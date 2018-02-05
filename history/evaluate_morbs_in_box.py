import os
import numpy as np
import time
import copy
import sys

import matplotlib
import matplotlib.pyplot as plt

import argparse

ang_2_bohr = 1.0/0.52917721067
hart_2_ev = 27.21138602

import cp2k_utilities as cu

parser = argparse.ArgumentParser(
    description='Calculates the molecular orbitals on a specified grid.')

parser.add_argument(
    '--cp2k_input',
    metavar='FILENAME',
    required=True,
    help='CP2K input of the SCF calculation.')
parser.add_argument(
    '--cp2k_output',
    metavar='FILENAME',
    required=True,
    help='CP2K output of the SCF calculation.')
parser.add_argument(
    '--basis_file',
    metavar='FILENAME',
    required=True,
    help='File containing the used basis sets.')
parser.add_argument(
    '--xyz_file',
    metavar='FILENAME',
    required=True,
    help='.xyz file containing the geometry.')
parser.add_argument(
    '--restart_file',
    metavar='FILENAME',
    required=True,
    help='Restart file containing the final wavefunction.')
parser.add_argument(
    '--output_file',
    metavar='FILENAME',
    required=True,
    help='Output containing the molecular orbitals and supporting info.')

parser.add_argument(
    '--emin',
    type=float,
    metavar='E',
    required=True,
    help='Lowest energy value for selecting orbitals (eV).')
parser.add_argument(
    '--emax',
    type=float,
    metavar='E',
    required=True,
    help='Highest energy value for selecting orbitals (eV).')

parser.add_argument(
    '--z_top',
    type=float,
    metavar='H',
    required=True,
    help='Distance of the top plane of the evaluation region from \
          topmost atom (angstroms).')
parser.add_argument(
    '--dx',
    type=float,
    metavar='DX',
    required=True,
    help='Spatial step for the grid (angstroms).')
parser.add_argument(
    '--local_eval_box_size',
    type=float,
    metavar='D',
    default=18.0,
    help='Spatial step for the grid (angstroms).')

args = parser.parse_args()

### -----------------------------------------
### Read input files
### -----------------------------------------

time0 = time.time()
elem_basis_names, cell = cu.read_cp2k_input(args.cp2k_input)
print("Read cp2k input: %.3f" % (time.time()-time0))

time1 = time.time()
fermi = cu.read_fermi_from_cp2k_out(args.cp2k_output)
print("Fermi energy: %.6f" % fermi)
print("Read cp2k out: %.3f" % (time.time()-time1))

time1 = time.time()
at_positions, at_elems = cu.read_atoms(args.xyz_file)
print("Read xyz: %.3f" % (time.time()-time1))

time1 = time.time()
basis_sets = cu.read_basis_functions(args.basis_file, elem_basis_names)
print("Read basis sets: %.3f" % (time.time()-time1))

time1 = time.time()
morb_composition, morb_energies, morb_occs, ref_energy, i_homo = \
    cu.load_restart_wfn_file(args.restart_file, args.emin, args.emax, fermi)
print("Found %d orbitals" % len(morb_energies))
print("Read restart: %.3f" % (time.time()-time1))


### -----------------------------------------
### Define morb evaluation region
### -----------------------------------------

height_above_atoms = args.z_top # angstroms
height_below_atoms = 1.0

top_atom_z = np.max(at_positions[:, 2]) # Bohr
z_top = top_atom_z + height_above_atoms*ang_2_bohr
carb_positions = at_positions[np.array(at_elems)[:, 0] == 'C']
z_bottom = np.min(carb_positions[:, 2]) - height_below_atoms*ang_2_bohr# Bohr

eval_reg_size = np.array([cell[0], cell[1], z_top-z_bottom])

# Define real space grid
# Cp2k chooses close to 0.08 angstroms (?)
step = args.dx
step *= ang_2_bohr

eval_reg_size_n = (np.round(eval_reg_size/step)).astype(int)
dv = eval_reg_size/eval_reg_size_n

# increase the z size such that top plane exactly matches z_top
eval_reg_size[2] += dv[2]
eval_reg_size_n[2] += 1

# z array in bohr and wrt topmost atom
z_arr = np.arange(0.0, eval_reg_size[2], dv[2]) + z_bottom - top_atom_z

### -----------------------------------------
### Calculate the molecular orbitals in the specified region
### -----------------------------------------

morb_grids = cu.calc_morbs_in_region(eval_reg_size, eval_reg_size_n, z_bottom,
                at_positions, at_elems,
                basis_sets, morb_composition,
                pbc_box_size = args.local_eval_box_size)

time0 = time.time()
elim = np.array([args.emin, args.emax])
np.savez(args.output_file, morb_grids, morb_energies, dv, z_arr, elim)
print("Saved the orbitals to file: %.2fs" % (time.time() - time0))
