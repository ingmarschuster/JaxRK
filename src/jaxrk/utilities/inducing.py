import jax.numpy as np
from numpy.random import randn, rand
from jax import grad
from ..kern import Kernel
from scipy.optimize import minimize
import numpy as onp

__all__ = ["inducing_set"]


def __casted_output(function: callable) -> callable:
    """Cast the output of a function to np.float64

    Args:
        function (callable): Original function

    Returns:
        callable: Function with casted output
    """
    return lambda x: np.asarray(function(x), dtype=np.float64)


def inducing_set(points: np.array, k: Kernel, non_sparse_penalty: float = 1.0) -> tuple:
    """Compute an inducing set for a given set of points

    Args:
        points (np.array): Points to compute the inducing set for
        k (Kernel): Kernel to use
        non_sparse_penalty (float, optional): Penalty for non-sparse solutions. Defaults to 1.0.

    Returns:
        tuple: Matrix for approximation, selected inducing points, approximation distance, cost function
    """
    assert non_sparse_penalty > 0
    assert len(points) > 1
    assert len(points.shape) == 2
    N = len(points)
    I = np.eye(N)
    G = k(points)  # compute gram matrix

    def cost(A, lamb):
        """Cost function for inducing set"""
        assert len(lamb.shape) == 1
        assert lamb.size == A.shape[0] == A.shape[1]
        fact = I - A @ np.diag(lamb)
        return (np.trace(fact @ G @ fact.T) + non_sparse_penalty * lamb.sum()) / N

    def extract_params(params):
        """Extract parameters from flattened parameter vector"""
        return (params[N:].reshape((N, N)), params[:N])

    def flat_cost(params):
        """Cost function using flattened parameter vector"""
        A, lamb = extract_params(params)
        return cost(A, lamb)

    init = np.hstack([np.ones(N), np.eye(N).flatten()])
    bounds = [(0.0, 1.0)] * N
    bounds.extend([(None, None)] * N * N)

    rval = minimize(
        __casted_output(flat_cost),
        init,
        jac=__casted_output(grad(flat_cost)),
        bounds=bounds,
    )
    assert rval["success"], "Optimization unsuccessfull"
    A, lamb = extract_params(rval["x"])
    selected = lamb > 0.0
    not_selected = np.bitwise_not(selected)

    appr_matr = np.where(
        np.repeat(selected[:, np.newaxis], N, 1),
        I,  # point is selected, doesn't need to be approximated
        # point not selected, choose best approximation
        A @ np.diag(lamb),
    )
    fact = I - appr_matr
    m = np.sum(selected)
    distances = np.diag(fact @ G @ fact.T)
    assert m > 0, "No inducing points. Try smaller value for `non_sparse_penalty`"

    print(
        "Selected",
        m,
        "inducing points. Distance between approximation and original feature: excluded points mean  %f, all points mean %f."
        % (distances[not_selected].mean(), distances.mean()),
    )

    return (
        appr_matr,  # matrix for approximation
        selected,  # selected inducing points
        distances,  # approximation distance
        cost,  # cost function
    )
