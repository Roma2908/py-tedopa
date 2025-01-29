"""
This module comprises functions for simulating the time-evolution of one- and
two-site open quantum systems in a bosonic environment via :func:`tedopa1` and
:func:`tedopa2` and helper functions.

.. todo::
   Decide if better to convert the arguments of tedopa1 and tedopa2 to kwargs.

"""

import numpy as np

from tedopa import _recurrence_coefficients as rc
from tedopa import tmps


def tedopa1(h_loc, a, state, method, j, domain, ts_full, ts_system,
            trotter_compr=None, compr=None, g=1, trotter_order=2,
            num_trotter_slices=100, ncap=20000, v=0):
    """
    TEDOPA for a single site coupled to a bosonic bath.

    This function proceeds in two steps: (i) Map the Hamiltonian from a system
    composed of one site that is linearly coupled to a reservoir of bosonic
    modes with a given spectral function to the same site coupled to a 1D chain
    of bosonic modes and (ii) perform time evolution.

    The performed mapping is based on an algorithm introduced by Chin et al.
    in Journal of Mathematical Physics 51, 092109 (2010); doi: 10.1063/1.3490188.

    The inputs to this function include the initial state, the local
    Hamiltonian, the spectral density, time of evolution, query times and some
    performance parameters. The output provides the MPAs of the evolved state at
    the requested times.

    Args:
        h_loc (numpy.ndarray):
            Matrix representation of the local Hamiltonian of the one-site
            system.
        a (numpy.ndarray):
            Interaction operator. This is the site-part of the tensor product
            that comprises the interaction Hamiltonian and is defined as
            :math:`\\hat{A}` in Chin et al.
        state (mpnum.MPArray):
            The initial state of the system which is to be evolved.
        method (str):
            The parameterization of the intial state. Either 'mps', 'mpo' or
            'pmps'. Determines which method is used in the simulation.
        j (types.LambdaType):
            Spectral function :math:`J(\\omega)` as defined in Chin et al.
        domain (list[float]):
            Domain on which :math:`J(\\omega)` is defined, for example [0,
            np.inf]
        ts_full (list[float]):
            The times for which the evolution should be computed and the whole
            state chain returned.
        ts_system (list[float]):
            The times for which the evolution should be computed and the reduced
            density matrix of only the system should be returned.
        trotter_compr (dict):
            Compression parameters used in the iterations of Trotter (in the
            form required by :func:`mpnum.MPArray.compress`. If unsure, look at
            https://github.com/dseuss/mpnum/blob/master/examples/mpnum_intro.ipynb .)
            If omitted, some default compression will be used that will
            probably work but might lead to problems. See
            :func:`tmps._set_compr_params` for more information.
        compr (dict):
            Parameters for the compression which is executed on every MPA during
            the calculations, except for the Trotter calculation, where
            trotter_compr is used. compr = dict(method='svd', rank=10) would for
            example ensure that the ranks of any MPA never exceed 10 during all
            of the calculations. An accepted relative error for the
            compression can be provided in addition to or instead of ranks,
            which would lead to e.g.
            compr = dict(method='svd', rank=10, relerr=1e-12).
            If omitted, some default compression will be used that will
            probably work but might lead to problems. See
            :func:`tmps._set_compr_params` for more information.
        g (float):
            Cutoff :math:`g`, assuming that for :math:`J(\\omega)` it is
            :math:`g(\\omega)=g\\omega`.
        trotter_order (int):
            Order of Trotter - Suzuki decomposition to be used. Currently only 2
            and 4 are implemented
        num_trotter_slices (int):
            Number of Trotter slices to be used for the largest t in ts_full or
            ts_system. If ts_system=[10, 25, 30] and num_trotter_slices=100,
            then the program would use 100/30*10=33, 100/30*25=83 and
            100/30*30=100 Trotter slices to calculate the time evolution for the
            three times.
        ncap (int):
            Number internally used by py-orthpol to determine accuracy of the
            returned recurrence coefficients. Must be <= 60000, the higher the
            longer the calculation of the recurrence coefficients takes and the
            more accurate it becomes.
        v (int):
            Level of verbose output. 0 means no output, 1 means that some
            basic output showing the progress of calculations is produced. 2
            will in addition show the bond dimensions of the state after every
            couple of iterations, 3 will show bond dimensions after every
            Trotter iteration.

    Returns:
        list[list[float], list[mpnum.MPArray]]:
            The first list is an array of times for which the states are
            actually computed (might differ slightly from the times in ts_full
            and ts_system, since the ones in times have to be multiples of
            tau). The second list is an array of the corresponding evolved
            states.
    """
    state_shape = state.shape
    if len(domain) != 2:
        raise ValueError("Domain needs to be of the form [x1, x2]")
    if len(a) != state_shape[0][0]:
        raise ValueError(
            "Dimension of 'a' must be the same as that of the \
            first site of the chain.")
    if len(state_shape) < 2:
        raise ValueError("The provided state has no chain representing the \
                         mapped environment. Check state.shape.")

    if v != 0:
        print("Calculating the TEDOPA mapping...")
    singlesite_ops, twosite_ops = map(h_loc, a, state_shape,
                                      j, domain, g, ncap)
    if v != 0:
        print("Proceeding to tmps...")

    ts, subsystems = get_times(ts_full, ts_system, len(state), 0, 1)

    times, subsystems, states = tmps.evolve(
        state=state, hamiltonians=[singlesite_ops, twosite_ops], ts=ts,
        subsystems=subsystems,
        num_trotter_slices=num_trotter_slices, method=method,
        trotter_compr=trotter_compr, trotter_order=trotter_order,
        compr=compr, v=v)
    return times, states


def tedopa2(h_loc, a_twosite, state, method, sys_position, js,
            domains, ts_full, ts_system, trotter_compr=None, compr=None,
            gs=(1, 1), trotter_order=2, num_trotter_slices=100, ncap=20000,
            v=0):
    """
    TEDOPA for two sites coupled to each other and each individually to its own
    bosonic bath.

    This function proceeds in two steps: (i) Map the Hamiltonian from a system
    composed of two coupled sites that are each linearly coupled to their
    possibly distinct reservoir of bosonic modes with a given spectral
    function to a 1D chain representing the whole setup and (ii) perform time
    evolution.

    The performed mapping is based on an algorithm introduced by Chin et al.
    in Journal of Mathematical Physics 51, 092109 (2010); doi: 10.1063/1.3490188.

    The inputs to this function include the initial state, the local
    Hamiltonian, the spectral densities, time of evolution, query times and some
    performance parameters. The output provides the MPAs of the evolved state at
    the requested times.

    The first elements in the lists js, domains, etc. always refer to the
    first (left) site and the second elements in the lists refer to the
    second (right) site of the system

    Args:
        h_loc (numpy.ndarray):
            Matrix representation of the local Hamiltonian of the two-site
            system.
        a_twosite (list[numpy.ndarray]):
            List of two matrices, each of which represents the site-part of the
            tensor product interaction Hamiltonian for the two sites.
        state (mpnum.MPArray):
            The initial state of the system which is to be evolved.
        method (str):
            The parameterization of the intial state. Either 'mps', 'mpo' or
            'pmps'. Determines which method is used in the simulation.
        sys_position (int):
            Which index, in the chain representing the state, is the position of
            the first site of the system (starting at 0). E.g. sys_position = 2
            if the chain-length is is 6 and sites are of the form
            env-env-sys-sys-env-env.
        js (list[types.LambdaType]):
            Spectral functions :math:`J(\\omega)` for the two environments as
            defined by Chin et al.
        domains (list[list[float]]):
            Domains on which the :math:`J(\\omega)` are defined. Can be
            different for the two sites, for example, [[0, np.inf], [0,1]]
        ts_full (list[float]):
            The times for which the evolution should be computed and the whole
            state chain returned.
        ts_system (list[float]):
            The times for which the evolution should be computed and the reduced
            density matrix of only the system should be returned.
        trotter_compr (dict):
            Compression parameters used in the iterations of Trotter (in the
            form required by :func:`mpnum.MPArray.compress`. If unsure, look at
            https://github.com/dseuss/mpnum/blob/master/examples/mpnum_intro.ipynb .)
            If omitted, some default compression will be used that will
            probably work but might lead to problems. See
            :func:`tmps._set_compr_params` for more information.
        compr (dict):
            Parameters for the compression which is executed on every MPA during
            the calculations, except for the Trotter calculation, where
            trotter_compr is used. compr = dict(method='svd', rank=10) would for
            example ensure that the ranks of any MPA never exceed 10 during all
            of the calculations. An accepted relative error for the
            compression can be provided in addition to or instead of ranks,
            which would lead to e.g.
            compr = dict(method='svd', rank=10, relerr=1e-12).
            If omitted, some default compression will be used that will
            probably work but might lead to problems. See
            :func:`tmps._set_compr_params` for more information.
        gs (list[float]):
            List of cutoffs :math:`g`, assuming that for :math:`J(\\omega)`
            it is :math:`g(\\omega)=g\\omega`.
        trotter_order (int):
            Order of Trotter-Suzuki decomposition to be used. Currently only 2
            and 4 are implemented
        num_trotter_slices (int):
            Number of Trotter slices to be used for the largest t in ts_full or
            ts_system. If ts_system=[10, 25, 30] and num_trotter_slices=100,
            then the program would use 100/30*10=33, 100/30*25=83 and
            100/30*30=100 Trotter slices to calculate the time evolution for the
            three times.
        ncap (int):
            Number internally used by py-orthpol to determine accuracy of the
            returned recurrence coefficients. Must be <= 60000, the higher the
            longer the calculation of the recurrence coefficients takes and the
            more accurate it becomes.
        v (int):
            Level of verbose output. 0 means no output, 1 means that some
            basic output showing the progress of calculations is produced. 2
            will in addition show the bond dimensions of the state after every
            couple of iterations, 3 will show bond dimensions after every
            Trotter iteration.

    Returns:
        list[list[float], list[mpnum.MPArray]]:
            The first list is an array of times for which the states are
            actually computed (might differ slightly from the times in ts_full
            and ts_system, since the ones in times have to be multiples of
            tau). The second list is an array of the corresponding evolved
            states.
    """
    state_shape = state.shape
    if len(domains[0]) != 2 or len(domains[1]) != 2:
        raise ValueError("A domain needs to be of the form [x1, x2]")
    if len(a_twosite[0]) != state_shape[sys_position][0]:
        raise ValueError(
            "Dimension of 'a_twosite[0]' must be the same as that of the \
            first site of the system.")
    if len(a_twosite[1]) != state_shape[sys_position + 1][0]:
        raise ValueError(
            "Dimension of 'a_twosite[1]' must be the same as that of the \
            second site of the system.")
    if len(state_shape) < 3:
        raise ValueError("The provided state has no chain representing the \
                         mapped environment. Check state.shape.")

    if v != 0:
        print("Calculating the TEDOPA mapping...")
    left_ops = map(np.zeros([state_shape[sys_position][0]] * 2),
                   a_twosite[0], list(
            reversed(state_shape[:sys_position + 1:])),
                   js[0], domains[0], gs[0], ncap)
    singlesite_ops_left, twosite_ops_left = [list(reversed(i)) for i in
                                             left_ops]
    singlesite_ops_right, twosite_ops_right = \
        map(np.zeros([state_shape[sys_position + 1][0]] * 2), a_twosite[1],
            list(state_shape[sys_position + 1::]), js[1], domains[1],
            gs[1], ncap)
    singlesite_ops = singlesite_ops_left + singlesite_ops_right
    twosite_ops = twosite_ops_left + [h_loc] + twosite_ops_right

    if v != 0:
        print("Proceeding to tmps...")

    ts, subsystems = get_times(ts_full, ts_system, len(state), sys_position, 2)

    times, subsystems, states = tmps.evolve(
        state=state, hamiltonians=[singlesite_ops, twosite_ops], ts=ts,
        subsystems=subsystems, num_trotter_slices=num_trotter_slices,
        method=method, trotter_compr=trotter_compr, trotter_order=trotter_order,
        compr=compr, v=v)
    return times, states


def map(h_loc, a, state_shape, j, domain, g, ncap):
    """
    Map the Hamiltonian of one site coupled to bosonic environmentself.

    This function calculates the operators acting on every single site of the
    resulting chain and the operators acting on every two adjacent sites in the
    chain from the local Hamiltonian and the spectral density.

    The mapping is based on an algorithm introduced by Chin et al. in
    Journal of Mathematical Physics 51, 092109 (2010); doi: 10.1063/1.3490188.

    Args:
        h_loc (numpy.ndarray):
            Matrix representation of the local Hamiltonian of the one-site
            system.
        a (numpy.ndarray):
            Interaction operator. This is the site-part of the tensor product
            that comprises the interaction Hamiltonian and is defined as
            :math:`\\hat{A}` in Chin et al. doi: 10.1063 / 1.3490188
        state_shape (list[list[int]]):
            The shape of the chain on which the Hamiltonian is to be applied.
            For example [[3, 3], [2, 2], [2, 2]] for a system comprised of 3
            sites, where the first one has 2 physical legs each of dimension 3,
            the second has 2 physical legs each of dimension 2 and so on.
            This is the typical MPA shape used by ``mpnum``
            (``state.shape`` if ``state`` is an ``mpnum.MPArray``).
        j (types.LambdaType):
            Spectral function :math:`J(\\omega)` as defined in Chin et al.
            doi: 10.1063 / 1.3490188
        domain (list[float]):
            Domain on which :math:`J(\\omega)` is defined, for example [0,
            np.inf]
        g (float):
            Constant :math:`g`, assuming that for :math:`J(\\omega)` it is
            :math:`g(\\omega)=g\\omega`.
        ncap (int):
            Number internally used by py-orthpol.

    Returns:
        list[list[numpy.ndarray]]:
            Terms of the effective Hamiltonian acting on the chain after the
            chain mapping. Two lists, one with the single-site operators and the
            other with adjacent-site operators that act on two sites. See the
            input parameters of :func:`tmps.evolve`

    """
    params = _get_parameters(
        n=len(state_shape), j=j, domain=domain, g=g, ncap=ncap)
    dims_chain = [i[0] for i in state_shape]
    bs = [_get_annihilation_op(dim) for dim in dims_chain[1::]]
    b_daggers = [b.T for b in bs]
    return _get_singlesite_ops(h_loc, params, bs, b_daggers), \
           _get_twosite_ops(a, params, bs, b_daggers)


def _get_singlesite_ops(h_loc, params, bs, b_daggers):
    """
    List of the operators acting on every single site after chain mapping

    Args:
        h_loc (numpy.ndarray): Local Hamiltonian
        params (list): Parameters as returned by :func:`_get_parameters`
        bs (list): The list of annihilation operators acting on each site
            of the chain
        b_daggers (list): The list of creation operators acting on each site
            of the chain

    Returns:
        list: List of operators acting on every single site
    """
    omegas, ts, c0 = params
    singlesite_ops = [omegas[i]
                      * b_daggers[i].dot(bs[i]) for i in range(len(bs))]
    singlesite_ops = [h_loc] + singlesite_ops

    return singlesite_ops


def _get_twosite_ops(a, params, bs, b_daggers):
    """
    List of the operators acting on every two adjacent sites after chain mapping

    Args:
        a (numpy.ndarray):
            Interaction operator provided by the user
        params (list):
            Parameters as returned by :func:`_get_parameters`
        bs (list):
            The list of annihilation operators acting on each site of the chain
        b_daggers (list):
            The list of creation operators acting on each site of the chain

    Returns:
        list:
            List of operators acting on every two adjacent sites
    """
    omegas, ts, c0 = params
    twosite_ops = [ts[i] * (
            np.kron(bs[i], b_daggers[i + 1]) + np.kron(b_daggers[i], bs[i + 1]))
                   for
                   i in range(len(bs) - 1)]
    twosite_ops = [c0 * np.kron(a, bs[0] + b_daggers[0])] + twosite_ops

    return twosite_ops


def _get_parameters(n, j, domain, g, ncap):
    """
    Calculate the parameters needed for mapping the Hamiltonian to a 1D chain

    Args:
        n (int):
            Number of recurrence coefficients required
            (:func:`rc.recurrenceCoefficients` actually returns one more and the
            system site does not need one, so the argument n-2 is passed)
        j (types.LambdaType):
            Spectral function :math:`J(\\omega)` as defined in Chin et al.
            doi: 10.1063 / 1.3490188
        domain (list[float]):
            Domain on which :math:`J(\\omega)` is defined, for example [0,
            np.inf]
        g (float):
            Constant :math:`g`, assuming that for :math:`J(\\omega)` it is
            :math:`g(\\omega)=g\\omega`.
        ncap (int):
            Number internally used by py-orthpol to determine accuracy of
            the returned recurrence coefficients. Must be <= 60000,
            the higher the longer the calculation of the recurrence
            coefficients takes and the more accurate it becomes.

    Returns:
        list[list[float], list[float], float]:
            omegas, ts, c0 as defined in the paper
    """
    alphas, betas = rc.recurrenceCoefficients(n - 2, lb=domain[0], rb=domain[1],
                                              j=j, g=g, ncap=ncap)
    omegas = g * np.array(alphas)
    ts = g * np.sqrt(np.array(betas)[1::])
    c0 = np.sqrt(betas[0])
    return omegas, ts, c0


def _get_annihilation_op(dim):
    """
    Creates the annihilation operator

    Args:
        dim (int):
            Dimension of the site it should act on

    Returns:
        numpy.ndarray:
            The annihilation operator
    """
    op = np.zeros((dim, dim))
    for i in range(dim - 1):
        op[i, i + 1] = np.sqrt(i + 1)
    return op


def get_times(ts_full, ts_system, len_state, sys_position, sys_length):
    """
    This is a function specifically designed for TEDOPA systems. It calculates
    the proper 'ts' and 'subsystems' input lists for :func:`tmps.evolve` from a
    list of times where the full state shall be returned and a list of times
    where only the reduced state of the system in question shall be returned.
    ts then basically is a concatenation of ts_full and ts_system,
    while subsystems will indicate that at the respective time in ts either
    the full state or only a reduced density matrix should be returned.

    Args:
        ts_full (list[float]):
            List of times where the full state including environment chain
            should be returned
        ts_system (list[float]):
            List of times where only the reduced density matrix of the system
            should be returned
        len_state (int):
            The length of the state
        sys_position (int):
            The position of the system (first site would be 0)
        sys_length (int):
            Length of the system, i.e. number of sites the system is
            comprised of

    Returns:
        tuple(list[float], list[list[int]]):
            Times and subsystems in the form that has to be provided to
            :func:`tmps.evolve`
    """
    ts = list(ts_full) + list(ts_system)
    subsystems = [[0, len_state]] * len(ts_full) + \
                 [[sys_position, sys_position + sys_length]] * len(ts_system)
    return ts, subsystems
