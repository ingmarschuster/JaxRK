import jax.numpy as np
import jax.scipy as sp
from jax import vmap, jit, pmap
from jax import random
from functools import partial
from ..core.typing import PRNGKeyT, Array


vinvert = jit(vmap(np.linalg.inv))
vcholesky = jit(vmap(partial(sp.linalg.cholesky, lower=True)))

select_rows = jit(vmap(lambda sel, inp: sel @ inp, (0, None)))
sym_matmul_fixed_inp = jit(vmap(lambda sel, inp: sel @ inp @ sel.T, (0, None)))
sym_matmul_variable_inp = jit(
    vmap(
        lambda sel, inp: sel @ inp @ sel.T,
    )
)

vmatmul_fixed_inp = jit(vmap(lambda sel, inp: sel @ inp, (0, None)))
vmatmul_variable_inp = jit(
    vmap(
        lambda sel, inp: sel @ inp,
    )
)


def loo_train_val(n_orig: int) -> tuple[Array]:
    """Get leave-one-out train and validation indices

    Args:
        n_orig (int): Number of samples in original dataset

    Returns:
        tuple[Array]: Train and validation indices

    Example:
        >>> loo_train_val(5)
        (DeviceArray([[1, 2, 3, 4],
                      [0, 2, 3, 4],
                      [0, 1, 3, 4],
                      [0, 1, 2, 4],
                      [0, 1, 2, 3]], dtype=int32),
        DeviceArray([[0],
                     [1],
                     [2],
                     [3],
                     [4]], dtype=int32))

    """
    val = np.arange(n_orig)
    train = np.array([np.delete(val, i) for i in val])
    return train, val.reshape(-1, 1)


def cv_train_val(n_orig: int, n_train: int, n_splits: int, rng: PRNGKeyT) -> tuple[Array]:
    """Get cross-validation train and validation indices

    Args:
        n_orig (int): Number of samples in original dataset
        n_train (int): Number of samples to use in training set
        n_splits (int): Number of splits
        rng (PRNGKeyT): Random number generator key

    Returns:
        tuple[Array]: Train and validation indices

    Example:
        >>> cv_train_val(5, 3, 2, random.PRNGKey(0))
        (DeviceArray([[2, 3, 1],
                      [1, 0, 4]], dtype=int32),
        DeviceArray([[0, 4],
                     [3, 2]], dtype=int32))
    """
    p = vmap(random.permutation, (0, None))(random.split(rng, n_splits), n_orig)
    return p[:, :n_train], p[:, n_train:]


def idcs_to_selection_matr(n_orig: int, idcs: Array, idcs_sorted: bool = False) -> Array:
    """Convert submatrix indices to linear maps that perform the actual selection.

    Args:
        n_orig (int): Size of original matrix from which we select rows/columns
        idcs (Array): row/colum indices. Each row is converted into its own linear map.
        idcs_sorted (bool, optional): Whether indices are sorted in ascending order. Defaults to False.

    Returns:
        Array: Linear maps corresponding to the indices in each row.

    Example:
        >>> idcs_to_selection_matr(5, np.array([[0, 2, 3], [1, 2, 3]]))
        DeviceArray([[[1., 0., 0., 0., 0.],
                      [0., 0., 1., 0., 0.],
                      [0., 0., 0., 1., 0.]],x

                     [[0., 1., 0., 0., 0.],
                      [0., 0., 1., 0., 0.],
                      [0., 0., 0., 1., 0.]]], dtype=float32)
    """
    if not idcs_sorted:
        idcs = np.sort(idcs, 1)
    rval = np.zeros((*idcs.shape, n_orig))
    for split, vi in enumerate(idcs):
        for r, c in enumerate(vi):
            rval = rval.at[split, r, c].set(1.0)
            # Old implementation was:
            # rval = rval.at[index[split, r, c]].set(1.)
    return rval


def invert_submatr(gram: Array, train_idcs: Array, zerofill: bool = True) -> Array:
    """Invert square gram-submatrices for cross validation scheme

    Args:
        gram (Array): Full gram matrix
        train_idcs (Array): row/colum indices for selecting submatrices from gram. One row contains indices for one submatrix.
        zerofill (bool, optional): Wether to fill non-selected rows/colums with zero after inversion, so submatrix-inverses match gram in shape. Defaults to True.

    Returns:
        Array: The matrices computed by first computing submatrices, inverting, and optionally filling non-selected rows/colums with zero.
    """
    train_sel_matr = idcs_to_selection_matr(gram.shape[0], train_idcs)
    rval = vinvert(sym_matmul_fixed_inp(train_sel_matr, gram))
    if zerofill:
        rval = sym_matmul_variable_inp(np.swapaxes(train_sel_matr, -1, -2), rval)
    return rval


def cholesky_submatr(gram: Array, train_idcs: Array, zerofill: bool = True) -> Array:
    """Cholesky decompose square gram-submatrices for cross validation scheme

    Args:
        gram (Array): Full gram matrix
        train_idcs (Array): row/colum indices for selecting submatrices from gram. One row contains indices for one submatrix.
        zerofill (bool, optional): Wether to fill non-selected rows/colums with zero after inversion, so submatrix-inverses match gram in shape. Defaults to True.

    Returns:
        Array: The matrices computed by first computing submatrices, computing the lower Cholesky factor, and optionally filling non-selected rows/colums with zero.
    """
    train_sel_matr = idcs_to_selection_matr(gram.shape[0], train_idcs)
    rval = vcholesky(sym_matmul_fixed_inp(train_sel_matr, gram))
    if zerofill:
        rval = sym_matmul_variable_inp(np.swapaxes(train_sel_matr, -1, -2), rval)
    return rval
