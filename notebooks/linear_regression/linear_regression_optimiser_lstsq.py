"""Polynomial Linear regression solved by an least-squares optimiser

This file sets up an example from setting up problem to running the inversion:
- For the problem: polynomial linear regression,
- Using the tool: non-linear least-squares optimiser (scipy.optimize.least_squares)

The function we are going to fit is: y = -6 - 5x + 2x^2 + x^3

We may also write the polynomial curves in this form: y = sum(m_n * x^n), n=0,1,2,3,
where: m_n, n=0,1,2,3 are the model coefficients.

If we consider N data points and M=3 model parameters, then N equations like above 
yields a linear operation: d = Gm,
where: d refers to data observations (y_1, y_2, ..., y_N).T
       G refers to basis matrix: ( (1, x_1, x_1^2, x_1^3)
                                   (1, x_2, x_2^2, x_2^3)
                                   ...
                                   (1, x_N, x_N^2, x_N^3) )
       m refers to the unknown model parameters (m_0, m_1, m_2, m_3)

Note that G matrix can also be called the Jacobian as it is the first derivative of
forward operator with respect to the unknown model. We refer to the function that 
calculates G matrix given a set of x as the basis function.

"""

############# 0. Import modules #######################################################

import numpy as np
import matplotlib.pyplot as plt
from cofi import BaseProblem, InversionOptions, Inversion

np.random.seed(42)

show_plot = False
show_summary = True

def main():

    ######### 1. Define the problem ###################################################

    # generate data with random Gaussian noise
    def basis_func(x):
        return np.array([x**i for i in range(4)]).T                           # x -> G
    _m_true = np.array([-6,-5,2,1])                                           # m

    sample_size = 20                                                          # N
    x = np.random.choice(np.linspace(-3.5,2.5), size=sample_size)             # x
    def forward_func(m):
        return basis_func(x) @ m                                              # m -> y_synthetic
    y_observed = forward_func(_m_true) + np.random.normal(0,1,sample_size)    # d

    if show_plot:
        _x_plot = np.linspace(-3.5,2.5)
        _G_plot = basis_func(_x_plot)
        _y_plot = _G_plot @ _m_true
        plt.figure(figsize=(12,8))
        plt.plot(_x_plot, _y_plot, color="darkorange", label="true model")
        plt.scatter(x, y_observed, color="lightcoral", label="observed data")
        plt.xlabel("X")
        plt.ylabel("Y")
        plt.legend()
        plt.show()

    # define the problem in cofi
    inv_problem = BaseProblem()
    inv_problem.name = "Polynomial Regression"
    inv_problem.set_data(y_observed)
    inv_problem.set_forward(forward_func)
    inv_problem.set_initial_model(np.ones(4))
    if show_summary:
        inv_problem.summary()


    ############# 2. Define the inversion options #####################################
    inv_options = InversionOptions()
    inv_options.set_tool("scipy.optimize.least_squares")
    if show_summary:
        inv_options.summary()


    ############# 3. Start an inversion ###############################################
    inv = Inversion(inv_problem, inv_options)
    inv_result = inv.run()
    if show_summary:
        inv_result.summary()


    ############# 4. Plot result ######################################################
    if show_plot:
        _x_plot = np.linspace(-3.5,2.5)
        _G_plot = basis_func(_x_plot)
        _y_plot = _G_plot @ _m_true
        _y_synth = _G_plot @ inv_result.model
        plt.figure(figsize=(12,8))
        plt.plot(_x_plot, _y_plot, color="darkorange", label="true model")
        plt.plot(_x_plot, _y_synth, color="seagreen", label="least-squares optimisation solution")
        plt.scatter(x, y_observed, color="lightcoral", label="original data")
        plt.xlabel("X")
        plt.ylabel("Y")
        plt.legend()
        plt.show()


if __name__ == "__main__":
    main()
