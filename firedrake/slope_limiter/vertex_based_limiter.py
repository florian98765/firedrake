from __future__ import absolute_import
from firedrake import dx, assemble, LinearSolver, MIN, MAX
from firedrake.interpolation import Interpolator
from firedrake.function import Function
from firedrake.functionspace import FunctionSpace
from firedrake.parloops import par_loop, READ, RW
from firedrake.ufl_expr import TrialFunction, TestFunction
from firedrake.slope_limiter.limiter import Limiter
__all__ = ("VertexBasedLimiter",)


class VertexBasedLimiter(Limiter):
    """
    A vertex based limiter for P1DG fields.

    This limiter implements the vertex-based limiting scheme described in
    Dmitri Kuzmin, "A vertex-based hierarchical slope limiter for p-adaptive
    discontinuous Galerkin methods". J. Comp. Appl. Maths (2010)
    http://dx.doi.org/10.1016/j.cam.2009.05.028
    """

    def __init__(self, space):
        """
        Initialise limiter

        :param space : FunctionSpace instance
        """

        self.P1DG = space
        self.P1CG = FunctionSpace(self.P1DG.mesh(), 'CG', 1)  # for min/max limits
        self.P0 = FunctionSpace(self.P1DG.mesh(), 'DG', 0)  # for centroids

        # Storage containers for cell means, max and mins
        self.centroids = Function(self.P0)
        self.max_field = Function(self.P1CG)
        self.min_field = Function(self.P1CG)
        self.centroid_solver = self._construct_centroid_solver()
        self.max_interpolate = Interpolator(self.centroids, self.max_field, access=MAX)
        self.min_interpolate = Interpolator(self.centroids, self.min_field, access=MIN)

        # Perform limiting loop
        self._limit_kernel = """
double alpha = 1.0;
double qavg = qbar[0][0];
for (int i=0; i < q.dofs; i++) {
    if (q[i][0] > qavg)
        alpha = fmin(alpha, fmin(1, (qmax[i][0] - qavg)/(q[i][0] - qavg)));
    else if (q[i][0] < qavg)
        alpha = fmin(alpha, fmin(1, (qavg - qmin[i][0])/(qavg - q[i][0])));
}
for (int i=0; i<q.dofs; i++) {
    q[i][0] = qavg + alpha*(q[i][0] - qavg);
}
                             """

    def _construct_centroid_solver(self):
        """
        Constructs a linear problem for computing the centroids

        :return: LinearSolver instance
        """
        u = TrialFunction(self.P0)
        v = TestFunction(self.P0)
        a = assemble(u * v * dx)
        return LinearSolver(a, solver_parameters={'ksp_type': 'preonly',
                                                  'pc_type': 'bjacobi',
                                                  'sub_pc_type': 'ilu'})

    def _update_centroids(self, field):
        """
        Update centroid values
        """
        b = assemble(TestFunction(self.P0) * field * dx)
        self.centroid_solver.solve(self.centroids, b)

    def compute_bounds(self, field):
        """
        Only computes min and max bounds of neighbouring cells
        """
        self._update_centroids(field)
        self.max_field.assign(-1.0e10)  # small number
        self.min_field.assign(1.0e10)  # big number

        # FIXME: Relies on implementation detail in PyOP2
        # since op2.RW does not work the way it was expected to
        # we are using op2.WRITE in all cases and it happens to
        # read and write from the buffer
        self.min_interpolate.interpolate()
        self.max_interpolate.interpolate()

    def apply_limiter(self, field):
        """
        Only applies limiting loop on the given field
        """
        par_loop(self._limit_kernel, dx,
                 {"qbar": (self.centroids, READ),
                  "q": (field, RW),
                  "qmax": (self.max_field, READ),
                  "qmin": (self.min_field, READ)})

    def apply(self, field):
        """
        Re-computes centroids and applies limiter to given field
        """
        assert field.function_space() == self.P1DG, \
            'Given field does not belong to this objects function space'

        self.compute_bounds(field)
        self.apply_limiter(field)