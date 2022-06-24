import matplotlib.pyplot as plt
import numpy as np

import pygimli
from pygimli import meshtools
from pygimli.physics import ert

from cofi import BaseProblem, InversionOptions, Inversion
from cofi.solvers import BaseSolver


############# ERT Modelling with PyGIMLi ##############################################

world = meshtools.createWorld(start=[-55,0], end=[105,-80], worldMarker=True)
conductive_anomaly = meshtools.createCircle(pos=[10,-7], radius=5, marker=2)
geom = world + conductive_anomaly
ax = pygimli.show(geom)
ax[0].figure.savefig("figs/true_geometry")

scheme = ert.createData(elecs=np.linspace(start=0, stop=50, num=51), schemeName="dd")
for s in scheme.sensors():
    geom.createNode(s + [0.0, -0.2])

rhomap = [[1, 200], [2,  50],]

mesh = meshtools.createMesh(geom, quality=33)
ax = pygimli.show(mesh, data=rhomap, label="$\Omega m$", showMesh=True)
ax[0].figure.savefig("figs/true_model_coarse")

# mesh = mesh.createH2()
# ax = pygimli.show(mesh, data=rhomap, label="$\Omega m$", showMesh=True)
# ax[0].figure.savefig("figs/true_model")

data = ert.simulate(mesh, scheme=scheme, res=rhomap, noiseLevel=1,
                    noiseAbs=1e-6, seed=42)

data.remove(data['rhoa'] < 0)
log_data = np.log(data['rhoa'].array())
ax = ert.show(data)
ax[0].figure.savefig("figs/data")

############# Inverted by PyGIMLi solvers #############################################

# mgr = ert.ERTManager(data)
# inv = mgr.invert(lam=20, verbose=True)
# fig = mgr.showResultAndFit()
# fig.savefig("figs/invert_result")


############# Extra info from PyGIMLi, required by our own solver #####################

forward_operator = ert.ERTModelling(sr=False, verbose=False)
forward_operator.setComplex(False)
forward_operator.setData(scheme)
forward_operator.setMesh(mesh, ignoreRegionManager=True)

start_model = np.ones(mesh.cellCount()) * 80.0

region_manager = forward_operator.regionManager()
region_manager.setMesh(mesh)
region_manager.setConstraintType(2)
Wm = pygimli.matrix.SparseMapMatrix()
region_manager.fillConstraints(Wm)
Wm = pygimli.utils.sparseMatrix2coo(Wm)

def get_response(model, forward_operator):
    return np.log(np.array(forward_operator.response(model)))

def get_residual(model, log_data, forward_operator):
    response = get_response(model, forward_operator)
    residual = log_data - response
    return residual

def get_jacobian(model, forward_operator):
    response = get_response(model, forward_operator)
    forward_operator.createJacobian(model)
    J = np.array(forward_operator.jacobian())
    jac = J / np.exp(response[:, np.newaxis]) * np.exp(np.log(model))[np.newaxis, :]
    return jac

def get_jac_residual(model, log_data, forward_operator):
    response = get_response(model, forward_operator)
    residual = log_data - response
    forward_operator.createJacobian(model)
    J = np.array(forward_operator.jacobian())
    jac = J / np.exp(response[:, np.newaxis]) * np.exp(np.log(model))[np.newaxis, :]
    return jac, residual

def get_data_misfit(model, log_data, forward_operator):
    residual = get_residual(model, log_data, forward_operator)
    return residual.T @ residual

def get_regularisation(model, Wm, lamda):
    return lamda * (Wm @ model).T @ (Wm @ model)

def get_objective(model, log_data, forward_operator, Wm, lamda):
    data_misfit = get_data_misfit(model, log_data, forward_operator)
    regularisation = get_regularisation(model, Wm, lamda)
    obj = data_misfit + regularisation
    return obj

def get_gradient(model, log_data, forward_operator, Wm, lamda):
    jac, residual = get_jac_residual(model, log_data, forward_operator)
    data_misfit_grad =  - 2 * residual @ jac
    regularisation_grad = 2 * lamda * Wm.T @ Wm @ model
    return data_misfit_grad + regularisation_grad

def get_hessian(model, log_data, forward_operator, Wm, lamda):
    jac = get_jacobian(model, forward_operator)
    hess = jac.T @ jac + lamda * Wm.T @ Wm
    return hess


############# Inverted by our Gauss-Newton algorithm ##################################

# reference: 
# Carsten Rücker, Thomas Günther, Florian M. Wagner,
# pyGIMLi: An open-source library for modelling and inversion in geophysics,
# https://doi.org/10.1016/j.cageo.2017.07.011.

class GaussNewton(BaseSolver):
    def __init__(self, inv_problem, inv_options):
        __params = inv_options.get_params()
        self._niter = __params["niter"]
        self._verbose = __params["verbose"]
        self._model_0 = inv_problem.initial_model
        self._residual = inv_problem.residual
        self._jacobian = inv_problem.jacobian
        self._gradient = inv_problem.gradient
        self._hessian = inv_problem.hessian
        self._misfit = inv_problem.data_misfit if inv_problem.data_misfit_defined else None
        self._reg = inv_problem.regularisation if inv_problem.regularisation_defined else None

    def __call__(self):
        current_model = np.array(self._model_0)
        for i in range(self._niter):
            term1 = self._hessian(current_model)
            term2 = - self._gradient(current_model)
            model_update = np.linalg.solve(term1, term2)
            current_model = np.array(current_model + model_update)
            if self._verbose:
                print("-" * 80)
                print(f"Iteration {i+1}")
                if self._misfit: print(self._misfit(current_model))
                if self._reg: print(self._reg(current_model))
        return {"model": current_model, "success": True}

# hyperparameters
lamda = 20
niter = 100
inv_verbose = True

# CoFI - define BaseProblem
ert_problem = BaseProblem()
ert_problem.name = "Electrical Resistivity Tomography defined through PyGIMLi"
ert_problem.set_forward(get_response, args=[forward_operator])
ert_problem.set_jacobian(get_jacobian, args=[forward_operator])
ert_problem.set_residual(get_residual, args=[log_data, forward_operator])
ert_problem.set_data_misfit(get_data_misfit, args=[log_data, forward_operator])
ert_problem.set_regularisation(get_regularisation, args=[Wm, lamda])
ert_problem.set_gradient(get_gradient, args=[log_data, forward_operator, Wm, lamda])
ert_problem.set_hessian(get_hessian, args=[log_data, forward_operator, Wm, lamda])
ert_problem.set_initial_model(start_model)

# CoFI - define InversionOptions
inv_options = InversionOptions()
inv_options.set_tool(GaussNewton)
inv_options.set_params(niter=niter, verbose=inv_verbose)

# CoFI - define Inversion, run it
inv = Inversion(ert_problem, inv_options)
inv_result = inv.run()

# plot inferred model
inv_result.summary()
ax = pygimli.show(mesh, data=inv_result.model, label=r"$\Omega m$")
ax[0].set_title("Inferred model")
ax[0].figure.savefig("figs/pygimli_ert_gauss_newton_inferred")