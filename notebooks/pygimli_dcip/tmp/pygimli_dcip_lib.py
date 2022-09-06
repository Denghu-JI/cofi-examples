"""Wrappers around PyGIMLi library for DCIP problem

The file name should end with "_lib.py", otherwise our bot may fail when generating
scripts for Sphinx Gallery. Furthermore, we recommend the file name to start with your
forward problem name, to align well with the naming of Jupyter notebook.

"""

import numpy as np
import matplotlib.pyplot as plt

import pygimli
from pygimli import meshtools
from pygimli.physics import ert


############# Helper functions from PyGIMLi ###########################################

# Dipole Dipole (dd) measuring scheme
def survey_scheme(start=0, stop=50, num=51, schemeName="dd"):
    scheme = ert.createData(elecs=np.linspace(start=start, stop=stop, num=num),schemeName=schemeName)
    # switch potential electrodes to yield positive geometric factors
    # this is also done for the synthetic data inverted later
    # ref: https://www.pygimli.org/_examples_auto/3_dc_and_ip/plot_07_simple_complex_inversion.html
    m = scheme["m"]
    n = scheme["n"]
    scheme["m"] = n
    scheme["n"] = m
    scheme.set("k", [1 for _ in range(scheme.size())])
    return scheme

# true geometry, forward mesh and true model
def model_true(scheme, start=[-55, 0], end=[105, -80], anomalies_pos=[[10,-7],[40,-7]], anomalies_rad=[5,5]):
    world = meshtools.createWorld(start=start, end=end, worldMarker=True)
    anomalies = []
    for i, (pos, rad) in enumerate(zip(anomalies_pos, anomalies_rad)):
        anomaly_i = meshtools.createCircle(pos=pos, radius=rad, marker=i+2)
        anomalies.append(anomaly_i)
    geom = meshtools.mergePLC([world] + anomalies)
    for s in scheme.sensors():          # local refinement 
        geom.createNode(s + [0.0, -0.2])
    mesh = meshtools.createMesh(geom, quality=33)
    rhomap = [[1, pygimli.utils.complex.toComplex(100, 0 / 1000)],
                # Magnitude: 50 ohm m, Phase: -50 mrad
                [2, pygimli.utils.complex.toComplex(50, 0 / 1000)],
                [3, pygimli.utils.complex.toComplex(100, -50 / 1000)],]
    return mesh, rhomap

# generate synthetic data
def ert_simulate(mesh, scheme, rhomap, noise_level=0, noise_abs=1e-4):
    data_all = ert.simulate(mesh, scheme=scheme, res=rhomap,
                            noiseLevel=noise_level, noise_abs=noise_abs, seed=42)
    r_complex = data_all["rhoa"].array() * np.exp(1j * data_all["phia"].array())
    r_complex_log = np.log(r_complex)            # real: log magnitude; imaginary: phase [rad]
    data_err = data_all["rhoa"] * data_all["err"]
    data_err_log = np.log(data_err)
    data_cov_inv = np.eye(r_complex_log.shape[0]) / (data_err_log ** 2)
    return data_all, r_complex, r_complex_log, data_cov_inv

# PyGIMLi ert.ERTManager
def ert_manager(data, verbose=False):
    return ert.ERTManager(data, verbose=verbose, useBert=True)

# inversion mesh
def inversion_mesh(ert_manager):
    inv_mesh = ert_manager.createMesh(ert_manager.data)
    # print("model size", inv_mesh.cellCount())   # 1031
    ert_manager.setMesh(inv_mesh)
    return inv_mesh

# inversion mesh rectangular (the above is by default triangular)
def inversion_mesh_rect(ert_manager):
    x = np.linspace(start=-5, stop=55, num=40)
    y = np.linspace(start=-20,stop=0,num=10)
    inv_mesh = pygimli.createGrid(x=x, y=y, marker=2)
    inv_mesh = pygimli.meshtools.appendTriangleBoundary(inv_mesh, marker=1, xbound=50, ybound=50)
    # print("model size", inv_mesh.cellCount())    # 1213
    ert_manager.setMesh(inv_mesh)
    return inv_mesh

# inversion mesh rectangular (toy mesh, for testing emcee)
def inversion_mesh_rect_toy(ert_manager):
    x = np.linspace(start=-5, stop=55, num=15)
    y = np.linspace(start=-20,stop=0,num=6)
    inv_mesh = pygimli.createGrid(x=x, y=y, marker=2)
    inv_mesh = pygimli.meshtools.appendTriangleBoundary(inv_mesh, marker=1, xbound=50, ybound=50)
    # print("model size", inv_mesh.cellCount())    # 289
    ert_manager.setMesh(inv_mesh)
    return inv_mesh

# PyGIMLi ert.ERTModelling
def ert_forward_operator(ert_manager, scheme, inv_mesh):
    forward_operator = ert_manager.fop
    forward_operator.setComplex(True)
    forward_operator.setData(scheme)
    forward_operator.setMesh(inv_mesh, ignoreRegionManager=True)
    return forward_operator

# regularisation matrix
def reg_matrix(forward_oprt):
    region_manager = forward_oprt.regionManager()
    region_manager.setConstraintType(2)
    Wm = pygimli.matrix.SparseMapMatrix()
    region_manager.fillConstraints(Wm)
    Wm = pygimli.utils.sparseMatrix2coo(Wm)
    return Wm

# initialise model TODO
def starting_model(ert_manager, val=None):
    data = ert_manager.data
    start_val = val if val else np.median(data['rhoa'].array())     # this is how pygimli initialises
    start_model = np.ones(ert_manager.paraDomain.cellCount()) * start_val
    start_val_log = np.log(start_val)
    start_model_log = np.ones(ert_manager.paraDomain.cellCount()) * start_val_log
    return start_model, start_model_log

# convert model to numpy array TODO
def model_vec(rhomap, fmesh):
    model_true = pygimli.solver.parseArgToArray(rhomap, fmesh.cellCount(), fmesh)
    return model_true


############# Functions provided to CoFI ##############################################

## Note: all functions below assume the model in log space!

def get_response(model, forward_operator):
    x_re_im = np.exp(pygimli.utils.squeezeComplex(model))
    print(x_re_im)
    return np.log(np.array(forward_operator.response(x_re_im)))

def get_residual(model, log_data, forward_operator):
    response = get_response(model, forward_operator)
    residual = log_data - response
    return residual

def get_jacobian(model, forward_operator):
    response = get_response(model, forward_operator)
    forward_operator.createJacobian(np.exp(model))
    J = np.array(forward_operator.jacobian())
    jac = J / np.exp(response[:, np.newaxis]) * np.exp(model)[np.newaxis, :]
    return jac

def get_jac_residual(model, log_data, forward_operator):
    response = get_response(model, forward_operator)
    residual = log_data - response
    forward_operator.createJacobian(np.exp(model))
    J = np.array(forward_operator.jacobian())
    jac = J / np.exp(response[:, np.newaxis]) * np.exp(model)[np.newaxis, :]
    return jac, residual

def get_data_misfit(model, log_data, forward_operator, data_cov_inv=None):
    residual = get_residual(model, log_data, forward_operator)
    data_cov_inv = np.eye(log_data.shape[0]) if data_cov_inv is None else data_cov_inv
    return np.abs(residual.T @ data_cov_inv @ residual)

def get_regularisation(model, Wm, lamda):
    model = np.exp(model)
    return lamda * (Wm @ model).T @ (Wm @ model)

def get_objective(model, log_data, forward_operator, Wm, lamda, data_cov_inv=None):
    data_misfit = get_data_misfit(model, log_data, forward_operator, data_cov_inv)
    regularisation = get_regularisation(model, Wm, lamda)
    obj = data_misfit + regularisation
    return obj

def get_gradient(model, log_data, forward_operator, Wm, lamda, data_cov_inv=None):
    jac, residual = get_jac_residual(model, log_data, forward_operator)
    data_cov_inv = np.eye(log_data.shape[0]) if data_cov_inv is None else data_cov_inv
    data_misfit_grad =  - residual.T @ data_cov_inv @ jac
    regularisation_grad = lamda * Wm.T @ Wm @ np.exp(model)
    return data_misfit_grad + regularisation_grad

def get_hessian(model, log_data, forward_operator, Wm, lamda, data_cov_inv=None):
    jac = get_jacobian(model, forward_operator)
    data_cov_inv = np.eye(log_data.shape[0]) if data_cov_inv is None else data_cov_inv
    hess = jac.T @ data_cov_inv @ jac + lamda * Wm.T @ Wm
    return hess