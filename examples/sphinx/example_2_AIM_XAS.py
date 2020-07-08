#!/usr/bin/env python
"""
Anderson impurity model for NiO XAS (Under contruction)
================================================================================
Here we calculate the :math:`L`-edge XAS spectrum of an Anderson impurity model.
This is sometimes also called a charge-transfer multiplet model.
Everyone's favorite test case for this is NiO and we won't risk being original!

The model considers the Ni :math:`3d` orbitals interacting with a surrounding 
set of O :math:`2p` orbitals. NiO has a rocksalt structure in which all Ni 
atoms are surrounded by six O atoms in cubic symmetry. Based on this, 
one would assume that the NiO cluster used to simulate the crystal would 
need to contain :math:`6` spin-orbitals per O 
:math:`\\times 6` O atoms :math:`=36` oxygen 
spin-orbitals. As explained by, for example, Maurits Haverkort et al. in
[1]_ only 10 of these orbitals
interact with the Ni atom and solving the problem with :math:`10+10 = 20`
spin-orbitals is far faster. For more general calculations of this type you 
may see the Ni states being referred to as the impurity or metal and the
O states being called the bath or ligand.

We consider on-site crystal field, spin-orbit coupling, magnetic field and
Coulomb interactions for the impurity, which is hybridized with the bath by
defining hopping parameters and an energy difference between the impurity 
and bath. In this way, our spectrum can include processes where
electrons transition from the bath to the impurity.

The crystal field and hopping parameters for such a calculation can be
obtained from DFT. We will use values for NiO from
[1]_. 
"""
import edrixs
import numpy as np
import sys
import matplotlib.pyplot as plt
from mpi4py import MPI
import sympy

################################################################################
# Number of electrons
# ------------------------------------------------------------------------------
# When formulating problems of this type, one usually thinks of a nominal 
# valence for the impurity atom in this case :code:`nd = 8` and assume that the
# bath of :code:`norb_bath  = 10` O spin-orbitals is full. The solver that we will
# use can simulate multiple bath sites. In our case we specify 
# :code:`nbath  = 1` sites. Electrons will be able to transition from O to Ni
# during our calculation, but the total number of valance electrons :code:`v_noccu`
# will be conserved.
nd = 8
norb_d = 10
norb_bath  = 10 # number of spin-orbitals for each bath site
nbath = 1
v_noccu  = nd + nbath*norb_d
shell_name = ('d', 'p') # valence and core shells for XAS calculation

################################################################################
# Coulomb interactions 
# ------------------------------------------------------------------------------
# The atomic Coulomb interactions are usually initialized based on Hartree-Fock
# calculations from, for example,  
# `Cowan's code <https://www.tcd.ie/Physics/people/Cormac.McGuinness/Cowan/>`_.
# edrixs has a database of these. We get our desired values for Ni via
info  = edrixs.utils.get_atom_data('Ni', '3d', nd, edge='L3')

################################################################################
# The atomic values are typically scaled to account for screening in the solid. 
# Here we use 80% scaling. Let's write these out in full, so that nothing is 
# hidden. Values for :math:`U_{dd}` and :math:`U_{dp}` are from comparing theory 
# and experiment from .
scale_dd = 0.8
F2_dd = info['slater_i'][1][1] * scale_dd
F4_dd = info['slater_i'][2][1] * scale_dd
U_dd = 7.3
F0_dd = U_dd + edrixs.get_F0('d', F2_dd, F4_dd)

scale_dp = 0.8
F2_dp = info['slater_n'][4][1] * scale_dp
G1_dp = info['slater_n'][5][1] * scale_dp
G3_dp = info['slater_n'][6][1] * scale_dp
U_dp = 8.5
F0_dp = U_dp + edrixs.get_F0('dp', G1_dp, G3_dp)

slater = ([F0_dd, F2_dd, F4_dd],  # initial
          [F0_dd, F2_dd, F4_dd, F0_dp, F2_dp, G1_dp, G3_dp])  # with core hole

################################################################################
# Charge-transfer energy scales
# ------------------------------------------------------------------------------
# The charge-transfer :math:`\Delta` and Coulomb :math:`U_{dd}` :math:`U_{dp}`
# parameters determine the centers of the different electonic configurations 
# before they are split. Note that as electrons are moved one has to pay energy
# costs associated with both charge-transfer and Coulomb interactions. The
# energy splitting between the bath and impurity is consequently not simply 
# :math:`\Delta`. One must therefore determine the energies by solving
# a set of linear equations. See the :ref:`edrixs.utils functions <utils>` 
# for details. We can call these functions to get the impurity energy
# :math:`E_d`, bath energy :math:`E_L`, impurity energy with a core hole
# :math:`E_{dc}`, bath energy with a core hole :math:`E_{Lc}` and the 
# core hole energy :math:`E_p`.
# Is there another energy definition that works better?
Delta = 4.7
E_d, E_L = edrixs.CT_imp_bath(U_dd, Delta, nd)
E_dc, E_Lc, E_p = edrixs.CT_imp_bath_core_hole(U_dd, U_dp, Delta, nd)
message = ("E_d = {:.3f} eV\n"
           "E_L = {:.3f} eV\n"
           "E_dc = {:.3f} eV\n"
           "E_Lc = {:.3f} eV\n"
           "E_p = {:.3f} eV\n")
print(message.format(E_d, E_L, E_dc, E_Lc, E_p))


################################################################################
# The spin-orbit coupling for the valence electrons in the ground state, the
# valence electrons with the core hole present, and for the core hole itself
# are initialized using the atomic values.
zeta_d_i = info['v_soc_i'][0]
zeta_d_n = info['v_soc_n'][0]
c_soc = info['c_soc']

################################################################################
# Build matrices describing interactions
# ------------------------------------------------------------------------------
# edrixs uses complex spherical harmonics as its default basis set. If we want to
# use another basis set, we need to pass a matrix to the solver, which transforms
# from complex spherical harmonics into the basis we use. 
# The solver will use this matrix when implementing the Coulomb intereactions 
# using the :code:`slater` list of Coulomb parameters.
# Here it is easiest to 
# use real harmoics. We make the complex harmoics to real harmonics transformation
# matrix via
trans_c2n = edrixs.tmat_c2r('d',True)

################################################################################
# The crystal field and SOC needs to be passed to the solver by constructing
# the impurity matrix in the real harmonic basis. For cubic symmetry, we need
# to set the energies of the orbitals along the
# diagonal of the matrix. These need to be in pairs as there are two 
# spin-orbitals for each orbital energy. Python 
# `list comprehension <https://realpython.com/list-comprehension-python/>`_
# and
# `numpy indexing <https://numpy.org/doc/stable/reference/arrays.indexing.html>`_
# are used here. All these energy are shifted by :code:`d_energy`. Need to put a
# larger number for ten_dq otherwise spectrum looking wrong. I assume the bath levels
# below are implemented wrongly? Or is the issue with Hz =  0.120?
ten_dq = 0.56
CF = np.zeros((10, 10), dtype=np.complex)
diagonal_indices = np.arange(norb_d)

orbital_energies = np.array([e for orbital_energy in
                             [+0.6 * ten_dq, # dz2
                              -0.4 * ten_dq, # dzx
                              -0.4 * ten_dq, # dzy
                              +0.6 * ten_dq, # dx2-y2
                              -0.4 * ten_dq] # dxy)
                             for e in [orbital_energy]*2])


CF[diagonal_indices, diagonal_indices] = orbital_energies                  

################################################################################
# The valence band SOC is constructed in the normal way and transformed into the
# real harmonic basis.
soc = edrixs.cb_op(edrixs.atom_hsoc('d', zeta_d_i), edrixs.tmat_c2r('d', True))

################################################################################
# The total impurity matrices for the ground and core-hole statest are then
# the sum of crystal field and spin-orbit coupling with an energy adjustment
# as above.
imp_mat = CF + soc + E_d
imp_mat_n = CF + soc + E_dc

################################################################################
# The energy level of the bath(s) is described by a matrix where the row index 
# denotes which bath and the column index denotes which orbital. Here we have
# only one bath, with 10 spin-orbitals all of same energy set as above.
ten_dq_bath = 1.44
bath_level = np.full((nbath, norb_d), E_L, dtype=np.complex)
bath_level[0, :2] += ten_dq_bath*.6  # 3z2-r2
bath_level[0, 2:6] -= ten_dq_bath*.4  # zx/yz
bath_level[0, 6:8] += ten_dq_bath*.6  # x2-y2
bath_level[0, 8:] -= ten_dq_bath*.4  # xy
bath_level_n = np.full((nbath, norb_d), E_Lc, dtype=np.complex)
bath_level_n[0, :2] += ten_dq_bath*.6  # 3z2-r2
bath_level_n[0, 2:6] -= ten_dq_bath*.4  # zx/yz
bath_level_n[0, 6:8] += ten_dq_bath*.6  # x2-y2
bath_level_n[0, 8:] -= ten_dq_bath*.4  # xy

################################################################################
# The hybridization matrix describes the hopping between the bath
# to the impuirty. This is the same shape as the bath matrix. We take our
# values from Maurits Haverkort et al.'s DFT calculations
# `Phys. Rev. B 85, 165113 (2012) <https://doi.org/10.1103/PhysRevB.85.165113>`_ 
# More explanation about this and the T notation used elsewhere.
Veg = 2.06
Vt2g = 1.21
    
hyb = np.zeros((nbath, norb_d), dtype=np.complex)
hyb[0, :2] = Veg  # 3z2-r2
hyb[0, 2:6] = Vt2g  # zx/yz
hyb[0, 6:8] = Veg  # x2-y2
hyb[0, 8:] = Vt2g  # xy

################################################################################
# We now need to define the parameters describing the XAS. X-ray polariztion
# can be linear, circular, isotropic (appropriate for a powder).
poltype_xas = [('isotropic', 0)]
################################################################################
# edrixs uses the temperature in Kelvin to work out the population of the low-lying
# states via a Boltzmann distribution.
temperature = 300
################################################################################
# The x-ray beam is specified by the incident angle and azimuthal angle in radians
thin = 0 / 180.0 * np.pi
phi = 0.0
################################################################################
# these are with respect to the crystal field :math:`z` and :math:`x` axes 
# written above. (That is, unless you specify the :code:`loc_axis` parameter
# described in the :code:`edrixs.xas_siam_fort` function documenation.)

################################################################################
# The spectrum in the raw calculation is offset by the energy involved with the
# core hole state, which is roughly :math:`5 E_p`, so we offset the spectrum by
# this and use :code:`om_shift` as an a adjustable parameters for comparing 
# theory to experiment. We also use this to specify :code:`ominc_xas`
# the range we want to compute the spectrum over. The core hole lifetime
# broadening also needs to be set via :code:`gamma_c_stat`.
om_shift = 857.6
c_level = -om_shift - 5*E_p
ominc_xas = om_shift + np.linspace(-15, 25, 1000)

################################################################################
# The final state broadening is specified in terms of half width at half maxium
# You can either pass a constant value or an array the same size as
# :code:`om_shift` with varying values to simulate, for example, different state
# lifetimes for higher energy states.
gamma_c = np.full(ominc_xas.shape, 0.48/2)   

################################################################################
# Magnetic field is a three-component vector in eV specified with respect to the
# same local axis as the x-ray beam. Since we are considering a powder here
# we create an isotropic normalized vector. :code:`on_which = 'both'` specifies to
# apply the operator to the total spin plus orbital angular momentum as is
# appropriate for a physical external magnetic field. You can use 
# :code:`on_which = 'spin'` to apply the operator to spin in order to simulate
# magnetic order in the sample. The value of the Bohr Magneton can
# be useful for converting here :math:`\mu_B = 5.7883818012\times 10^{−5}` 
# eV/T. Confirm this is correct 
ext_B = np.array([0.01, 0.01, 0.01])/np.sqrt(3)
on_which = 'spin'
    
################################################################################
# The number crunching uses
# `mpi4py <https://mpi4py.readthedocs.io/en/stable/>`_. You can safely ignore 
# this for most purposes, but see 
# `Y. L. Wang et al., Computer Physics Communications 243, 151-165 (2019) <https://doi.org/10.1016/j.cpc.2019.04.018>`_ 
# if you would like more details.
# The main thing to remember is that you should call this script via::
#
#        mpirun -n <number of processors> python example_AIM_XAS.py
#
# where :code:`<number of processors>` is the number of processsors
# you'd like to us. Running it as normal will work, it will just be slower.

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size() 

################################################################################
# Calling the :code:`edrixs.ed_siam_fort` solver will find the ground state and
# write input files, *hopping_i.in*, *hopping_n.in*, *coulomb_i.in*, *coulomb_n.in*
# for following XAS (or RIXS) calculation. We need to specify :code:`siam_type=0`
# which says that we will pass *imp_mat*, *bath_level* and *hyb*.
# We need to specify :code:`do_ed = 1`. More details of why will be included
# later. 

do_ed = 1
eval_i, denmat, noccu_gs = edrixs.ed_siam_fort(
    comm, shell_name, nbath, siam_type=0, imp_mat=imp_mat, imp_mat_n=imp_mat_n,
    bath_level=bath_level, bath_level_n=bath_level_n, hyb=hyb, c_level=c_level,
    c_soc=c_soc, slater=slater, ext_B=ext_B,
    on_which=on_which, trans_c2n=trans_c2n, v_noccu=v_noccu, do_ed=do_ed,
    ed_solver=2, neval=50, nvector=3, ncv=100, idump=True)

################################################################################
# Let's check that we have all the electrons we think we have and print how 
# the electron are distributed between the Ni (impurity) and O (bath).
assert np.abs(noccu_gs - v_noccu) < 1e-6
impurity_occupation = np.sum(denmat[0].diagonal()[0:norb_d]).real
bath_occupation = np.sum(denmat[0].diagonal()[norb_d:]).real
print('Impurity occupation = {:.6f}\n'.format(impurity_occupation))
print('Bath occupation = {:.6f}\n'.format(bath_occupation))

################################################################################
# We see that 0.36 electrons move from the O to the Ni in the ground state. 
# 
# We can now construct the XAS spectrum edrixs by applying a transition
# operator to create the excitated state. We need to be careful to specify how 
# many of the low energy states are thermally populated. In this case 
# :code:`num_gs=3`. This can be determined by inspecting the function output. 
xas, xas_poles = edrixs.xas_siam_fort(
    comm, shell_name, nbath, ominc_xas, gamma_c=gamma_c, v_noccu=v_noccu, thin=thin,
    phi=phi, num_gs=3, nkryl=200, pol_type=poltype_xas, temperature=temperature
)


################################################################################
# Let's plot the data and save it just in case
fig, ax = plt.subplots()

ax.plot(ominc_xas, xas)
ax.set_xlabel('Energy (eV)')
ax.set_ylabel('XAS intensity')
ax.set_title('Anderson impurity model for NiO')

np.savetxt('xas.dat', np.concatenate((np.array([ominc_xas]).T, xas), axis=1))

################################################################################
# We often want to represent the ground state in terms of
# :math:`\\alpha|d^8> + \\beta|d^9 L> + \\gamma|d^10 L^2>`.

################################################################################
#
# .. rubric:: Footnotes
# 
# .. [1] Maurits Haverkort et al `Phys. Rev. B 85, 165113 (2012) <https://doi.org/10.1103/PhysRevB.85.165113>`_. If you use these values in a paper you should, of course, cite it.
#
# 
