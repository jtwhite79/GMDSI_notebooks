import os
import sys

import shutil
import matplotlib.pyplot as plt


import platform
import numpy as np
import pandas as pd


sys.path.append("..")
import flopy
import pyemu
import herebedragons as hbd

# the weight assigned to each head observation; the same value used in the
# control files we build in the tutorials that follow
HEAD_WEIGHT = hbd.HEAD_WEIGHT

# the weight we suggest for the sfr (gage) observations; the same value used
# for the streamflow observations throughout the rest of the part1 tutorials.
# It is a subjective choice - that is rather the point of this tutorial
SFR_WEIGHT = hbd.SFR_WEIGHT

# the time (in days) at which the forecasts are made - the end of the simulation
FORECAST_TIME = 4383.5

# the forecasts of interest; the same ones used throughout the part1 tutorials.
# maps forecast site name to the model output file it is found in
FORECASTS = {'HEADWATER': 'sfr.csv',
             'TAILWATER': 'sfr.csv',
             'TRGW-0-9-1': 'heads.csv'}


def phi(simulated, measured, weight):
    """the weighted sum-of-squared residuals - the same objective function
    that PESTPP-GLM and PESTPP-IES minimize"""
    residual = np.array(simulated) - np.array(measured)
    return np.sum((weight * residual) ** 2)


def add_1to1(ax):
    lims = [
        np.min([ax.get_xlim(), ax.get_ylim()]),  # min of both axes
        np.max([ax.get_xlim(), ax.get_ylim()]),  # max of both axes
    ]
    # now plot both limits against each other
    ax.plot(lims, lims, 'k-', alpha=0.75, zorder=0)
    return



def run_model(sim_ws, silent=False):
    """run MODFLOW 6 in `sim_ws`.

    MODFLOW is chatty - it writes a banner and a line for every stress period
    it solves. That is worth seeing at least once (it is how you check that the
    model actually ran), but it makes for a lot of scrolling when we are
    running the model over and over again. With `silent=True` the run output is
    captured instead of echoed. Either way, a failed run still raises.
    """
    if silent:
        # subprocess pipes MODFLOW's output instead of writing it to stdout
        pyemu.os_utils.run("mf6", cwd=sim_ws, use_sp=True, verbose=False)
    else:
        pyemu.os_utils.run("mf6", cwd=sim_ws)
    return


def get_model(silent=False):
    # folder containing original model files
    org_ws = os.path.join('..', '..', 'models', 'monthly_model_files_1lyr_newstress')

    # set a new workspace folder to avoid breaking things by mistake
    sim_ws = os.path.join('freyberg_mf6')

    # remove existing folder
    if os.path.exists(sim_ws):
        shutil.rmtree(sim_ws)

    # copy the original model folder across
    shutil.copytree(org_ws, sim_ws)

    hbd.prep_bins(sim_ws)

    run_model(sim_ws, silent=silent)

    # get measured data
    get_meas_data(sim_ws)

    # get the "true" values of the forecasts
    get_pred_data(sim_ws)

    return print(f'model files are in: {sim_ws}')


def update_par(k1=3, rch_factor=1, sfr_weight=0.0, plot_forecast=False,
               silent=False):
    """update parameter values, run the model and plot the outcomes.

    Args:
        k1 (`float`): hydraulic conductivity in layer 1
        rch_factor (`float`): recharge is multiplied by this factor
        sfr_weight (`float`): the weight assigned to the sfr (gage)
            observations. Zero (the default) leaves them out of phi entirely
        plot_forecast (`bool`): add a bar chart of forecast error
        silent (`bool`): don't echo MODFLOW's run output. Handy once you have
            seen the model run and just want to see the plots
    """
    # load simulation
    org_ws = os.path.join('..', '..', 'models', 'monthly_model_files_1lyr_newstress')
    sim_ws = os.path.join('freyberg_mf6')
    sim = flopy.mf6.MFSimulation.load(sim_ws=org_ws, verbosity_level=0)
    
    sim.set_sim_path(sim_ws)

    # load flow model
    gwf = sim.get_model()
    
    gwf.npf.k.set_data(k1)
    gwf.npf.set_all_data_external()
    #gwf.npf.write()

    rch = gwf.rch.recharge.get_data()

    rch.update((x, y*rch_factor) for x, y in rch.items())
    gwf.rch.recharge.set_data(rch)
    gwf.rch.set_all_data_external()
    #gwf.rch.write()

    # run the model
    sim.write_simulation(silent=silent)
    #sim.run_simulation()
    run_model(sim_ws, silent=silent)

    # plot results
    plot_simvsmeas(sim_ws, sfr_weight)

    # and, if asked, how we did on the things we actually care about
    if plot_forecast:
        plot_forecast_error(sim_ws)

    return

def add_plot_formatting():
    plt.xlabel('measured')
    plt.ylabel('simulated')
    plt.grid()
    plt.axis('square')
    return

def plot_simvsmeas(sim_ws, sfr_weight):
    plt.rcParams.update({'font.size': 12})

    obs_data = pd.read_csv(os.path.join(sim_ws, 'obs_data_ess.csv'))
    sim_heads = pd.read_csv(os.path.join(sim_ws, 'heads.csv'))
    sim_sfr = pd.read_csv(os.path.join(sim_ws, 'sfr.csv'))

    # only the observations with a non-zero weight are plotted, just like
    # only the observations with a non-zero weight contribute to phi
    ncol = 2 if sfr_weight > 0 else 1
    fig = plt.figure(figsize=(5*ncol, 5))

    ax = fig.add_subplot(1, ncol, 1)
    head_sites=['TRGW-0-3-8', 'TRGW-0-26-6']
    # the first entry is the steady state stress period; the twelve that follow
    # are the historic period for which we have measured data
    simvals = sim_heads[head_sites].iloc[1:13].values
    measvals = obs_data[[i.lower() for i in head_sites]].iloc[1:13].values

    ax.scatter( measvals, simvals)
    ax.set_title('Heads')
    add_1to1(ax)
    add_plot_formatting()
    head_phi = phi(simvals, measvals, HEAD_WEIGHT)
    ax.text(x=.05, y=.95, s=f'weight:{HEAD_WEIGHT}\nphi:{round(head_phi,2)}',
            transform=ax.transAxes, ha='left', va='top')

    sfr_phi = 0.0
    if sfr_weight > 0:
        ax = fig.add_subplot(1, ncol, 2)
        simvals = sim_sfr['GAGE-1'].iloc[1:13].values
        measvals = obs_data[('GAGE-1').lower()].iloc[1:13].values
        ax.scatter( measvals,simvals)
        ax.set_title('SFR')
        add_1to1(ax)
        add_plot_formatting()
        sfr_phi = phi(simvals, measvals, sfr_weight)
        ax.text(x=.05, y=.95, s=f'weight:{sfr_weight}\nphi:{round(sfr_phi,2)}',
                transform=ax.transAxes, ha='left', va='top')
        # with more than one observation type weighted, the composite phi is
        # what history-matching actually minimizes
        fig.suptitle(f'composite phi: {round(head_phi + sfr_phi, 2)}')

    fig.tight_layout()
    return


def plot_forecast_error(sim_ws):
    """bar chart of simulated minus "true" forecast value; one bar per
    forecast. Recall that we only know the "truth" because we made it up..."""
    plt.rcParams.update({'font.size': 12})
    truth = pd.read_csv(os.path.join(sim_ws, 'pred_data_ess.csv'), index_col=0)

    fig, axes = plt.subplots(1, len(FORECASTS), figsize=(3.5*len(FORECASTS), 3.5))
    for ax, (site, csvfile) in zip(np.atleast_1d(axes), FORECASTS.items()):
        sim_df = pd.read_csv(os.path.join(sim_ws, csvfile))
        sim = sim_df.loc[sim_df.time == FORECAST_TIME, site].values[0]
        meas = truth.loc[site, 'value']
        error = sim - meas

        ax.bar([0], [error], color='r', width=0.5)
        ax.axhline(0.0, color='k', lw=1.0)
        ax.set_xlim(-1, 1)
        ax.set_xticks([])
        # keep the zero line in view so the sign and size of the error read clearly
        if error != 0:
            ax.set_ylim(sorted([0, error*1.6]))
        ax.set_title(f'{site}\ntruth:{round(meas,2)}  simulated:{round(sim,2)}',
                     fontsize=11)
        ax.set_ylabel('forecast error (simulated - truth)')
    fig.suptitle('forecast error - the thing we actually care about')
    fig.tight_layout()
    return

def get_pred_data(tmp_d='freyberg_mf6'):
    """get the "true" values of the forecasts from the truth model. These are
    smoothed in the same manner as the measured data."""
    pred_data = pd.read_csv(os.path.join('..', '..', 'models',
                                         'daily_freyberg_mf6_truth', 'pred_data.csv'))
    pred_data.set_index('site', inplace=True)

    truth = {}
    for site in FORECASTS.keys():
        site_pred_data = pred_data.loc[site, :].copy()
        site_pred_data.index = site_pred_data.time
        sm = site_pred_data.value.rolling(window=20, center=True, min_periods=1).mean()
        truth[site] = sm.reindex([FORECAST_TIME], method="nearest").values[0]
    truth = pd.Series(truth, name='value')
    truth.index.name = 'site'
    truth.to_csv(os.path.join(tmp_d, 'pred_data_ess.csv'))
    return


def get_meas_data(tmp_d='freyberg_mf6'):
    # geat meas values
    shutil.copy2(os.path.join('..', '..', 'models', 'daily_freyberg_mf6_truth','obs_data.csv'),
                            os.path.join(tmp_d, 'obs_data.csv'))
    obs_data = pd.read_csv(os.path.join(tmp_d, 'obs_data.csv'))
    obs_data.site = obs_data.site.str.lower()
    obs_data.set_index('site', inplace=True)
    
    # restructure the observation data 
    obs_sites = obs_data.index.unique().tolist()
    #model_times = pst.observation_data.time.dropna().astype(float).unique()
    model_times = pd.read_csv(os.path.join(tmp_d, 'heads.csv')).time.values
    ess_obs_data = {}
    for site in obs_sites:
        #print(site)
        site_obs_data = obs_data.loc[site,:].copy()
        if isinstance(site_obs_data, pd.Series):
            site_obs_data.loc["site"] = site_obs_data.index.values
        if isinstance(site_obs_data, pd.DataFrame):
            site_obs_data.loc[:,"site"] = site_obs_data.index.values
            site_obs_data.index = site_obs_data.time
            sm = site_obs_data.value.rolling(window=20,center=True,min_periods=1).mean()
            sm_site_obs_data = sm.reindex(model_times,method="nearest")
        #ess_obs_data.append(pd.DataFrame9sm_site_obs_data)
        ess_obs_data[site] = sm_site_obs_data
    ess_obs_data = pd.DataFrame(ess_obs_data)
    ess_obs_data.to_csv(os.path.join(tmp_d, 'obs_data_ess.csv'))

if __name__ == "__main__":
    print('This is not the command you are looking for...')