
import os
import numpy as np
import time
import copy
import sys
import argparse

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as colors

import cp2k_utilities as cu

ang_2_bohr = 1.0/0.52917721067
hart_2_ev = 27.21138602

parser = argparse.ArgumentParser(
    description='Produces LDOS data from supplied molecular orbitals \
                 along x direction on a plane normal to z direction.')
parser.add_argument(
    '--npz_file',
    metavar='FILENAME',
    required=True,
    help='.npz file containing the molecular orbitals and supporting info.')
parser.add_argument(
    '--output_dir',
    metavar='FILENAME',
    required=True,
    help="Directory containing the output data.")
parser.add_argument(
    '--sts_plane_height',
    type=float,
    metavar='H',
    required=True,
    help="The height of the sts plane from the topmost atom in angstroms. "\
         "Must lie inside the box/plane or top of it (triggers extrapolation).")
parser.add_argument(
    '--sts_de',
    type=float,
    default=0.05,
    help="Energy discretization for STS. (eV)")
parser.add_argument(
    '--sts_fwhm',
    nargs='+',
    type=float,
    metavar='FWHM',
    help='Full width half maximums for the broadening of each orbital.')

parser.add_argument(
    '--work_function',
    type=float,
    metavar='WF',
    default=None,
    help="Work function in eV of the system (fermi and vacuum level difference)." \
         "For extrapolation either this or the hartree file is needed.")
parser.add_argument(
    '--hartree_file',
    metavar='FILENAME',
    default=None,
    help="Cube file containing the hartree potential." \
         "Only needed if sts_plane_height is out of the morb eval region.")

parser.add_argument(
    '--crop_dist_l',
    type=float,
    metavar='D',
    required=True,
    help="Crop distance from left side (either from the end or from a defect).")
parser.add_argument(
    '--crop_dist_r',
    type=float,
    metavar='D',
    required=True,
    help="Crop distance from right side (either from the end or from a defect).")
parser.add_argument(
    '--crop_defect_l',
    type=int,
    default=1,
    help="1 - crop distance wrt a defect; 0 - from the end; left side")
parser.add_argument(
    '--crop_defect_r',
    type=int,
    default=1,
    help="1 - crop distance wrt a defect; 0 - from the end; right side")


parser.add_argument(
    '--padding_x',
    type=float,
    default=300.0,
    help="Zero-padding added to the LDOS before Fourier transform.")
parser.add_argument(
    '--emin',
    type=float,
    default=-0.7,
    help="Min value of energy.")
parser.add_argument(
    '--emax',
    type=float,
    default=0.7,
    help="Max value of energy.")
parser.add_argument(
    '--lat_param',
    type=float,
    metavar='A',
    required=True,
    help="Lattice parameter of the system (needed for alignment and some plots).")


parser.add_argument(
    '--gammas',
    nargs='+',
    type=float,
    metavar='G',
    default=1.0,
    help='Gamma values for color scale control.')
parser.add_argument(
    '--vmax_coefs',
    nargs='+',
    type=float,
    metavar='VM',
    default=1.0,
    help='Only show proportion lower than specified on the color scale.')


args = parser.parse_args()

time0 = time.time()

output_dir = args.output_dir
if output_dir[-1] != '/':
    output_dir += '/'

npz_file_data = np.load(args.npz_file)

morb_grids = npz_file_data['morb_grids']
morb_energies = npz_file_data['morb_energies']
dv = npz_file_data['dv']
z_arr = npz_file_data['z_arr']
emin, emax = npz_file_data['elim']
ref_energy = npz_file_data['ref_energy']
geom_name = npz_file_data['geom_label']

z_bottom = z_arr[0]
z_top = z_arr[-1]
plane_index = int(np.round((args.sts_plane_height*ang_2_bohr - z_bottom)/dv[2]))

num_morbs = np.shape(morb_grids)[0]
eval_reg_size_n = np.shape(morb_grids[0])
eval_reg_size = dv*eval_reg_size_n

if plane_index > len(z_arr) - 1:
    # Extrapolation is needed!

    if args.work_function != None:
        morb_planes = cu.extrapolate_morbs(morb_grids[:, :, :, -1], morb_energies, dv,
                                             args.sts_plane_height*ang_2_bohr - z_top, True,
                                             work_function=args.work_function/hart_2_ev)
    elif args.hartree_file != None:

        time1 = time.time()
        hart_cube_data = cu.read_cube_file(args.hartree_file)
        print("Read hartree: %.3f" % (time.time()-time1))
        hart_plane = cu.get_hartree_plane_above_top_atom(hart_cube_data, args.sts_plane_height)
        hart_plane -= ref_energy/hart_2_ev
        print("Hartree on extrapolation plane: min: %.4f; max: %.4f; avg: %.4f (eV)" % (
                                                        np.min(hart_plane)*hart_2_ev,
                                                        np.max(hart_plane)*hart_2_ev,
                                                        np.mean(hart_plane)*hart_2_ev))
        morb_planes = cu.extrapolate_morbs(morb_grids[:, :, :, -1], morb_energies, dv,
                                             args.sts_plane_height*ang_2_bohr - z_top, True,
                                             hart_plane=hart_plane, use_weighted_avg=True)
    else:
        print("Work function or Hartree potential must be supplied if STS plane is out of region")
        exit()

else:
    morb_planes = np.zeros((num_morbs, eval_reg_size_n[0], eval_reg_size_n[1]))
    for i_mo in range(num_morbs):
        morb_planes[i_mo, :, :] =  morb_grids[i_mo, :, :, plane_index]

### ----------------------------------------------------------------
### Plot some orbitals for troubleshooting
### ----------------------------------------------------------------
time1 = time.time()

i_homo = 0
for i, en in enumerate(morb_energies):
    if en > 0.0:
        i_homo = i - 1
        break
    if np.abs(en) < 1e-6:
        i_homo = i

n_homo = 20
n_lumo = 20

select = np.arange(i_homo - n_homo + 1, i_homo + n_lumo + 1, 1)

sel_morbs = np.zeros((eval_reg_size_n[0], len(select)*eval_reg_size_n[1]))

for i, i_mo in enumerate(select):
    sel_morbs[:, i*eval_reg_size_n[1]:(i+1)*eval_reg_size_n[1]] = morb_planes[i_mo]

x_arr = np.arange(0, eval_reg_size[0], dv[0])
y_arr_inc = np.arange(0, len(select)*eval_reg_size[1], dv[1])
x_grid_inc, y_grid_inc = np.meshgrid(x_arr, y_arr_inc, indexing='ij')

max_val = np.max(sel_morbs)

plt.figure(figsize=(12, int(eval_reg_size_n[1]/eval_reg_size_n[0]*12*len(select))))
plt.pcolormesh(x_grid_inc, y_grid_inc, sel_morbs, vmax=max_val, vmin=-max_val, cmap='seismic') # seismic bwr
plt.axis('off')
plt.axhline(n_homo*eval_reg_size[1], color='lightgray')
plt.savefig(output_dir+"orbs_h%.1f.png"%args.sts_plane_height, dpi=200, bbox_inches='tight')
plt.close()

print("Made orbital plot: %.3f" % (time.time()-time1))


### ----------------------------------------------------------------
### Calculate the LDOS based on the orbitals
### ----------------------------------------------------------------

de = args.sts_de

e_arr = np.arange(emin, emax+de, de)

x_arr_ang = np.arange(0.0, eval_reg_size_n[0]*dv[0], dv[0])/ang_2_bohr

x_e_grid, e_grid = np.meshgrid(x_arr_ang, e_arr, indexing='ij')

def calculate_ldos(de, fwhm, broad_type):

    def lorentzian(x):
        gamma = 0.5*fwhm
        return gamma/(np.pi*(x**2+gamma**2))

    def gaussian(x):
        sigma = fwhm/2.3548
        return np.exp(-x**2/(2*sigma**2))/(sigma*np.sqrt(2*np.pi))

    pldos = np.zeros((eval_reg_size_n[0], len(e_arr)))

    for i_mo, morb_plane in enumerate(morb_planes):
        en = morb_energies[i_mo]
        avg_morb = np.mean(morb_plane**2, axis=1)

        if broad_type == 'l':
            morb_ldos_broad = np.outer(avg_morb, lorentzian(e_arr - en))
        else:
            morb_ldos_broad = np.outer(avg_morb, gaussian(e_arr - en))

        pldos += morb_ldos_broad

    return pldos


def ldos_postprocess(ldos_raw, geom_name, height, fwhm, x_arr_whole, e_arr_whole):

    dx = x_arr_whole[1]-x_arr_whole[0]

    ### -------------------------------------------------------
    ### Crop the LDOS in space
    ### -------------------------------------------------------

    e_averaged = np.mean(ldos_raw, axis=1)
    first_half = e_averaged[:len(e_averaged)//2]
    second_half = e_averaged[len(e_averaged)//2:]

    crop_x_l = args.crop_dist_l
    if args.crop_defect_l != 0:
        index_l = np.argmax(first_half)
        crop_x_l = x_arr_whole[index_l] + args.crop_dist_l

    crop_x_r = args.crop_dist_r
    if args.crop_defect_r != 0:
        index_r = np.argmax(second_half) + len(first_half)
        crop_x_r = x_arr_whole[index_r] - args.crop_dist_r

    # align cropping, such that remaining area is a multiple of lattice parameter (minus dx!)
    lattice_param = args.lat_param
    crop_len = crop_x_r - crop_x_l
    crop_len_goal = np.round(crop_len/lattice_param)*lattice_param - dx
    extra_shift = (crop_len_goal - crop_len)/2

    crop_x_l -= extra_shift
    crop_x_r += extra_shift

    crop_l = int(np.round(crop_x_l/dx))
    # shift the other end due to putting on grid error
    crop_x_r += np.round(crop_x_l/dx)*dx - crop_x_l
    crop_r = int(np.round(crop_x_r/dx))

    x_arr = np.copy(x_arr_whole[crop_l:crop_r+1])
    ldos = np.copy(ldos_raw[crop_l:crop_r+1])

    crop_x_l_final = x_arr[0]
    crop_x_r_final = x_arr[-1]

    ### -------------------------------------------------------
    ### Crop the LDOS in energy
    ### -------------------------------------------------------

    e_arr = np.copy(e_arr_whole)
    if e_arr[0] < args.emin:
        index = np.argmax(e_arr>args.emin)-1
        e_arr = e_arr[index:]
        ldos = ldos[:, index:]
    if e_arr[-1] > args.emax:
        index = np.argmax(e_arr>args.emax)+1
        e_arr = e_arr[:index]
        ldos = ldos[:, :index]

    print("dx", dx)
    align_check = (x_arr[-1]-x_arr[0])%lattice_param
    print("alignment check:", align_check, align_check - lattice_param)

    ### -------------------------------------------------------
    ### Remove row avg and add padding
    ### -------------------------------------------------------

    def remove_row_average(ldos):
        ldos_no_avg = np.copy(ldos)
        for i in range(np.shape(ldos)[1]):
            ldos_no_avg[:, i] -= np.mean(ldos[:, i])
        return ldos_no_avg

    def add_padding(x_arr, ldos, padding_x, lattice_param):
        if padding_x <= 0.0:
            return x_arr, ldos
        dx = x_arr[1]-x_arr[0]
        init_len = x_arr[-1]-x_arr[0]

        # align resulting x-length to lattice param
        pad_len = init_len+2*padding_x
        pad_len_goal = np.round(pad_len/lattice_param)*lattice_param - dx
        padding_x = (pad_len_goal - init_len)/2

        pad_n_l = int(np.round(padding_x/dx))
        pad_x_l = pad_n_l*dx
        grid_shift = padding_x - pad_x_l
        pad_n_r = int(np.round((padding_x+grid_shift)/dx))
        pad_x_r = pad_n_r*dx

        padded_x_arr = np.arange(x_arr[0]-pad_x_l, x_arr[-1]+pad_x_r+1e-6, dx)
        padded_ldos = np.zeros((np.shape(ldos)[0]+pad_n_l+pad_n_r, np.shape(ldos)[1]))
        padded_ldos[pad_n_l:-pad_n_r] = ldos

        return padded_x_arr, padded_ldos

    ldos = remove_row_average(ldos)

    x_arr, ldos = add_padding(x_arr, ldos, args.padding_x, lattice_param)

    align_check = (x_arr[-1]-x_arr[0])%lattice_param
    print("alignment check:", align_check, align_check - lattice_param)

    ### -------------------------------------------------------
    ### Take the Fourier Transform
    ### -------------------------------------------------------

    def fourier_transform(ldos, dx, lattice_param):

        ft = np.fft.rfft(ldos, axis=0)
        aft = np.abs(ft)

        # Corresponding k points
        k_arr = 2*np.pi*np.fft.rfftfreq(len(ldos[:, 0]), dx)
        # Note: Since we took the FT of the charge density, the wave vectors are
        #       twice the ones of the underlying wave function.
        #k_arr = k_arr / 2

        # Lattice spacing for the ribbon = 3x c-c distance
        # Brillouin zone boundary [1/angstroms]
        bzboundary = np.pi / lattice_param

        dk = k_arr[1]
        bzb_index = int(np.round(bzboundary/dk))+1

        return k_arr, aft, dk, bzboundary, bzb_index

    k_arr, aft, dk, bzboundary, bzb_index = fourier_transform(ldos, dx, lattice_param)

    ### -------------------------------------------------------
    ### Save FT data to npz
    ### -------------------------------------------------------

    file_name = "ldos_%s_h%.1f_dx%.3f_fwhm%.2f%s" % (geom_name, height, dx, fwhm, broad_type)

    figname = file_name + "_crop%.0f%s_%.0f%s_e%.1f_%.1f_pad%.0f" % (
        args.crop_dist_l, 'f' if args.crop_defect_l == 0 else 't',
        args.crop_dist_r, 'f' if args.crop_defect_r == 0 else 't',
        args.emin, args.emax, args.padding_x)

    np.savez(output_dir+figname,x_arr=k_arr, y_arr=e_arr, values=aft,
            x_label="k (1/angstrom)", y_label="E (eV)")

    ### -------------------------------------------------------
    ### Make plots
    ### -------------------------------------------------------


    x_grid_whole, e_grid_whole = np.meshgrid(x_arr_whole, e_arr_whole, indexing='ij')
    k_grid, e_k_grid = np.meshgrid(k_arr, e_arr, indexing='ij')

    gamma_ldos = 0.5
    vmax_coef_ldos = 0.5

    for gamma in args.gammas:
        for vmax_coef in args.vmax_coefs:

            f, (ax1, ax2) = plt.subplots(2, figsize=(18.0, 12.0))

            ax1.pcolormesh(x_grid_whole, e_grid_whole, ldos_raw,
                            norm=colors.PowerNorm(gamma=gamma_ldos),
                            vmax=vmax_coef_ldos*np.max(ldos_raw),
                            cmap='gist_ncar')
            ax1.axvline(crop_x_l_final, color='r')
            ax1.axvline(crop_x_r_final, color='r')
            ax1.text(crop_x_l_final+1.0, e_arr_whole[0]+0.01, "%.2f"%crop_x_l_final, color='red')
            ax1.text(crop_x_r_final+1.0, e_arr_whole[0]+0.01, "%.2f"%crop_x_r_final, color='red')
            ax1.axhline(e_arr[0], color='r')
            ax1.axhline(e_arr[-1], color='r')
            ax1.set_xlabel("x (angstrom)")
            ax1.set_ylabel("E (eV)")

            ax2.pcolormesh(k_grid, e_k_grid, aft,
                            norm=colors.PowerNorm(gamma=gamma),
                            vmax=vmax_coef*np.max(aft),
                            cmap='gist_ncar')
            ax2.set_ylim([np.min(e_arr), np.max(e_arr)])
            ax2.set_xlim([0.0, 5*bzboundary])
            ax2.text(5*bzboundary-0.6, e_arr[0]+0.01, "max=%.2e"%np.max(aft), color='red')
            ax2.set_xlabel("k (1/angstrom)")
            ax2.set_ylabel("E (eV)")

            plt.savefig(output_dir+figname+"_g%.1f_vmc%.1f.png"%(gamma, vmax_coef), dpi=300, bbox_inches='tight')
            plt.close()



fwhm_arr = args.sts_fwhm

height = args.sts_plane_height

for fwhm in fwhm_arr:
    for broad_type in ['g']:

        time1 = time.time()
        print("----Calculating ldos for fwhm", fwhm)
        pldos = calculate_ldos(de, fwhm, broad_type)
        print("----Ldos calc time: %.2f"%(time.time()-time1))

        time1 = time.time()
        print("----Postprocessing fwhm", fwhm)
        ldos_postprocess(pldos, geom_name, height, fwhm, x_arr_ang, e_arr)
        print("----Postprocessing time: %.2f"%(time.time()-time1))

print("Completed in %.1f s" % (time.time()-time0))
