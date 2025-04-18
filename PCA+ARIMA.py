# PCA+ARIMA Macroeconomic Forecasting Code
# The codes attached below apply the Principal Component Analysis for reducing the dimensionality of macroeconomic factors and forecast the principal macroeconomic factor using ARIMA.

# =============================================================================
# Import libraries
# =============================================================================
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import sklearn
from sklearn.decomposition import PCA
import pmdarima as pm
import statsmodels.api as sm
import statsmodels.stats.diagnostic as smd
from statsmodels.stats.stattools import durbin_watson
from scipy.stats import shapiro
import statsmodels.stats.api as sms
from statsmodels.stats.outliers_influence import variance_inflation_factor
import warnings
import os

warnings.filterwarnings("ignore")

# =============================================================================
# Key Parameters
# =============================================================================
variance_threshold = 0.8
p_value_threshold = 0.1
r2_threshold = 0.05
predict_period = 9
n_normal = 1
n_extreme = 3
date_s = '2015-12-31'


# =============================================================================
# Custom Functions
# =============================================================================

def apply_pca(data, variance_threshold=0.8):
    """Apply PCA and select components based on variance threshold."""
    try:
        if data.shape[1] < 2:
            raise ValueError("Input data must have at least 2 columns for PCA")
        pca_model = PCA(n_components=min(data.shape[1], data.shape[0]))
        pca_model.fit(data)
        variance_cumsum = np.cumsum(pca_model.explained_variance_ratio_)
        num_pc = next((i + 1 for i, val in enumerate(variance_cumsum) if val >= variance_threshold), data.shape[1])
        if num_pc == 0:
            raise ValueError("No components meet variance threshold")
        pca_train = PCA(n_components=num_pc)
        pca_result = pca_train.fit_transform(data)
        df_pca_result = pd.DataFrame(pca_result, index=data.index, columns=[f'PC{i}' for i in range(num_pc)])
        if df_pca_result.isna().any().any():
            raise ValueError("PCA result contains NaNs")
        return df_pca_result, pca_train, num_pc
    except Exception as e:
        raise ValueError(f"PCA failed: {e}")


def forecast_pcs(pca_data, n_periods, seasonal_period=4):
    """Forecast principal components using Auto-ARIMA."""
    try:
        forecasts = []
        for i in range(pca_data.shape[1]):
            tmp_model = pm.auto_arima(
                pca_data.iloc[:, i],
                start_p=1, start_q=1, max_p=5, max_q=5,
                m=seasonal_period, d=None, seasonal=True,
                information_criterion='bic', test='kpss',
                trace=False, error_action='ignore', suppress_warnings=True
            )
            forecast = tmp_model.predict(n_periods=n_periods)
            forecasts.append(forecast)
        forecast_df = pd.DataFrame(
            np.array(forecasts).T,
            index=pd.date_range(start=pd.Timestamp('2023-09-30'), periods=n_periods, freq='Q'),
            columns=[f'PC{i}' for i in range(pca_data.shape[1])]
        )
        return forecast_df
    except Exception as e:
        raise ValueError(f"ARIMA forecasting failed: {e}")


# =============================================================================
# Read Input Data
# =============================================================================
try:
    macro_data = pd.read_excel("https://raw.githubusercontent.com/ELFEEEEE86/code/main/Input_Data_2023.6.xlsx", sheet_name="Macro_Data")
    macro_list = pd.read_excel("https://raw.githubusercontent.com/ELFEEEEE86/code/main/Input_Data_HASE_RETAIL_PD_2023.9.xlsx", sheet_name="Code")
except Exception as e:
    raise FileNotFoundError("Input files not found or could not be read from GitHub") from e

# Subset data
macro_data['Indicator'] = pd.to_datetime(macro_data['Indicator'])
macro_data.set_index('Indicator', inplace=True)
macro_data_all = macro_data[macro_data.index >= date_s]
macro_data_10Y = macro_data[macro_data.index >= '2015-12-31']

# Filter indicators
macro_list_candidates = list(macro_list[macro_list['Model included'] == 'Y']['Indicator abbreviation'])
macro_list_candidates_code = list(macro_list[macro_list['Model included'] == 'Y']['Indicator abbreviation'])
mapping_dict = dict(zip(macro_list_candidates, macro_list_candidates_code))
macro_list_sign = macro_list[macro_list['Model included'] == 'Y'][['Indicator abbreviation', 'sign']].set_index('Indicator abbreviation')

# Select relevant columns
macro_data_all = macro_data_all[macro_list_candidates]
macro_data_10Y = macro_data_10Y[macro_list_candidates]

# Handle missing values
macro_data_filled = macro_data_all.interpolate(method='linear')
macro_data_10Y_filled = macro_data_10Y.interpolate(method='linear')
macro_data_filled.dropna(inplace=True)
macro_data_10Y_filled.dropna(inplace=True)

# Validate data
for df, name in [(macro_data_filled, 'macro_data_filled'), (macro_data_10Y_filled, 'macro_data_10Y_filled')]:
    if df.empty:
        raise ValueError(f"{name} is empty after interpolation")
    if not df.select_dtypes(include=[np.number]).columns.equals(df.columns):
        raise ValueError(f"{name} contains non-numeric columns")
    if df.shape[1] < 2:
        raise ValueError(f"{name} has fewer than 2 columns; PCA requires multiple variables")

# Standardize data
Mean = macro_data_filled.mean(numeric_only=True)
Std = macro_data_filled.std(ddof=1, numeric_only=True)
Std_10Y = macro_data_10Y_filled.std(ddof=1, numeric_only=True)

for var, name in [(Mean, 'Mean'), (Std, 'Std'), (Std_10Y, 'Std_10Y')]:
    if not isinstance(var, pd.Series) or var.empty:
        raise ValueError(f"{name} is not a valid Series; check input data")

macro_data_normalized = (macro_data_filled - Mean) / Std

# =============================================================================
# PCA Analysis
# =============================================================================
df_pca_result, pca_model, num_pc = apply_pca(macro_data_normalized, variance_threshold)

# =============================================================================
# Univariate Regression
# =============================================================================
univariate_info = []
for macro_var in macro_data_normalized.columns:
    tmp_dep = macro_data_normalized[macro_var]
    for i in range(num_pc):
        tmp_ind = df_pca_result[f'PC{i}']
        if tmp_ind.isna().any() or tmp_ind.nunique() <= 1:
            continue
        X = sm.add_constant(tmp_ind)
        model = sm.OLS(tmp_dep, X)
        LR = model.fit()
        p_value = LR.pvalues.get(1, np.nan)
        univariate_info.append({
            'macro_variable': macro_var,
            'pca_component': i,
            'r_squared': LR.rsquared,
            'p_value': p_value
        })

df_univariate_info = pd.DataFrame(univariate_info)
df_univariate_info_filter = df_univariate_info[
    (df_univariate_info['p_value'].notna()) &
    (df_univariate_info['p_value'] < p_value_threshold) &
    (df_univariate_info['r_squared'] > r2_threshold)
    ]

# Multivariate regression with diagnostics
coef_total, p_value_total, ind_name_total, dep_name_total = [], [], [], []
r_squared_total, reset_test, DW_test, sharp_test, BP_test, VIF_test = [], [], [], [], [], []

for macro_var in macro_data_normalized.columns:
    tmp_ind_list = df_univariate_info_filter[
        df_univariate_info_filter['macro_variable'] == macro_var
        ]['pca_component']
    if tmp_ind_list.empty:
        continue
    tmp_ind = df_pca_result[[f'PC{i}' for i in tmp_ind_list]]
    X = sm.add_constant(tmp_ind)
    y = macro_data_normalized[macro_var]
    model = sm.OLS(y, X)
    LR = model.fit()

    reset_pvalue = smd.linear_reset(LR, power=2, test_type="fitted", use_f=True).pvalue
    dw_pvalue = durbin_watson(LR.resid)
    shapiro_pvalue = shapiro(LR.resid)[1]
    bp_test = sms.het_breuschpagan(LR.resid, LR.model.exog)[1]
    vif_values = [variance_inflation_factor(X.values, i) for i in range(X.shape[1])]

    tmp_ind_list_new = ['Intercept'] + [f'PC{i}' for i in tmp_ind_list]
    dep_name_total.extend([macro_var] * len(tmp_ind_list_new))
    ind_name_total.extend(tmp_ind_list_new)
    coef_total.extend(LR.params)
    p_value_total.extend(LR.pvalues)
    r_squared_total.extend([LR.rsquared] * len(tmp_ind_list_new))
    reset_test.extend([reset_pvalue] * len(tmp_ind_list_new))
    DW_test.extend([dw_pvalue] * len(tmp_ind_list_new))
    sharp_test.extend([shapiro_pvalue] * len(tmp_ind_list_new))
    BP_test.extend([bp_test] * len(tmp_ind_list_new))
    VIF_test.extend(vif_values)

df_pca_regression = pd.DataFrame({
    'macro_variable': dep_name_total,
    'principal': ind_name_total,
    'coef': coef_total,
    'p_value': p_value_total,
    'r_squared': r_squared_total,
    'reset_test': reset_test,
    'DW_test': DW_test,
    'sharp_test': sharp_test,
    'BP_test': BP_test,
    'VIF_test': VIF_test
})

# =============================================================================
# Forecast PCs
# =============================================================================
df_pca_result_predict_base = forecast_pcs(df_pca_result, predict_period)

# Reconstruct forecasts
predict_list = list(df_pca_result_predict_base.index)
df_pca_regression_predict_base = df_pca_regression.copy()

sum_dict = {f"{tmp_predict}_predict": sum for tmp_predict in predict_list}
for tmp_predict in predict_list:
    tmp_predict_pca = df_pca_result_predict_base.loc[tmp_predict].values
    tmp_df = pd.DataFrame(
        tmp_predict_pca,
        index=[f'PC{i}' for i in range(num_pc)],
        columns=[tmp_predict]
    ).reset_index().rename(columns={'index': 'principal'})
    df_pca_regression_predict_base = pd.merge(
        df_pca_regression_predict_base,
        tmp_df,
        left_on='principal',
        right_on='principal',
        how='left'
    )
    df_pca_regression_predict_base.fillna(1, inplace=True)  # Intercept
    if tmp_predict not in df_pca_regression_predict_base.columns:
        raise ValueError(f"Column {tmp_predict} not found after merge")
    df_pca_regression_predict_base[f"{tmp_predict}_predict"] = (
            df_pca_regression_predict_base['coef'] * df_pca_regression_predict_base[tmp_predict]
    )

df_pca_result_base = df_pca_regression_predict_base.groupby('macro_variable').agg(sum_dict)

# De-normalize
predict_list_new = df_pca_result_base.columns
df_Mean = Mean.to_frame(name='mean')
df_Std = Std.to_frame(name='std')
df_Std_10Y = Std_10Y.to_frame(name='std_10Y')
df_pca_result_base = pd.concat([df_pca_result_base, df_Mean, df_Std, df_Std_10Y], axis=1)

df_pca_regression_predict_final_base = pd.DataFrame()
for tmp_predict in predict_list_new:
    tmp_de_normalize = df_pca_result_base[tmp_predict] * df_Std['std'] + df_Mean['mean']
    tmp_de_normalize.name = tmp_predict
    df_pca_regression_predict_final_base = pd.concat(
        [df_pca_regression_predict_final_base, tmp_de_normalize], axis=1
    )

# Historical bounds
df_max = macro_data_filled.max(numeric_only=True).to_frame(name='max')
df_min = macro_data_filled.min(numeric_only=True).to_frame(name='min')
df_max_10Y = macro_data_10Y_filled.max(numeric_only=True).to_frame(name='max_10Y')
df_min_10Y = macro_data_10Y_filled.min(numeric_only=True).to_frame(name='min_10Y')

df_pca_regression_predict_final = pd.concat(
    [df_pca_regression_predict_final_base, df_Std, df_Std_10Y, df_max, df_min, df_max_10Y, df_min_10Y, macro_list_sign],
    axis=1
)

# Scenarios
df_pca_regression_predict_final_opt = pd.DataFrame()
df_pca_regression_predict_final_pes = pd.DataFrame()
df_pca_regression_predict_final_ext_opt = pd.DataFrame()
df_pca_regression_predict_final_ext_pes = pd.DataFrame()

for tmp_period in df_pca_regression_predict_final_base.columns:
    df_pca_regression_predict_final_opt[tmp_period] = (
            df_pca_regression_predict_final[tmp_period] +
            n_normal * df_pca_regression_predict_final['std_10Y'] * df_pca_regression_predict_final['sign']
    )
    df_pca_regression_predict_final_pes[tmp_period] = (
            df_pca_regression_predict_final[tmp_period] -
            n_normal * df_pca_regression_predict_final['std_10Y'] * df_pca_regression_predict_final['sign']
    )
    df_pca_regression_predict_final_ext_opt[tmp_period] = (
            df_pca_regression_predict_final[tmp_period] +
            n_extreme * df_pca_regression_predict_final['std_10Y'] * df_pca_regression_predict_final['sign']
    )
    df_pca_regression_predict_final_ext_pes[tmp_period] = (
            df_pca_regression_predict_final[tmp_period] -
            n_extreme * df_pca_regression_predict_final['std_10Y'] * df_pca_regression_predict_final['sign']
    )

# =============================================================================
# Output
# =============================================================================
working_dir = r'C:\Users\Desktop'
# The address of output， please modify accordingly.

output_path = f"{working_dir}/macro_data_predict.xlsx"
with pd.ExcelWriter(output_path) as writer:
    df_pca_regression_predict_final_base = pd.concat([macro_data_filled, df_pca_regression_predict_final_base.T])
    df_pca_regression_predict_base.rename(columns=mapping_dict, inplace=True)
    df_pca_regression_predict_final_base.to_excel(writer, sheet_name="Standard")

    df_pca_regression_predict_final_opt = pd.concat([macro_data_filled, df_pca_regression_predict_final_opt.T])
    df_pca_regression_predict_final_opt.rename(columns=mapping_dict, inplace=True)
    df_pca_regression_predict_final_opt.to_excel(writer, sheet_name="Optimistic")

    df_pca_regression_predict_final_pes = pd.concat([macro_data_filled, df_pca_regression_predict_final_pes.T])
    df_pca_regression_predict_final_pes.rename(columns=mapping_dict, inplace=True)
    df_pca_regression_predict_final_pes.to_excel(writer, sheet_name="Pessimistic")

    df_pca_regression_predict_final_ext_opt = pd.concat([macro_data_filled, df_pca_regression_predict_final_ext_opt.T])
    df_pca_regression_predict_final_ext_opt.rename(columns=mapping_dict, inplace=True)
    df_pca_regression_predict_final_ext_opt.to_excel(writer, sheet_name="over-Optimistic")

    df_pca_regression_predict_final_ext_pes = pd.concat([macro_data_filled, df_pca_regression_predict_final_ext_pes.T])
    df_pca_regression_predict_final_ext_pes.rename(columns=mapping_dict, inplace=True)
    df_pca_regression_predict_final_ext_pes.to_excel(writer, sheet_name="over-Pessimistic")

    df_pca_regression.to_excel(writer, sheet_name="pca regression")
    df_pca_result.to_excel(writer, sheet_name="pca Historical")
    df_pca_result_base.to_excel(writer, sheet_name="pca Forecasted")
    df_pca_result_predict_base.to_excel(writer, sheet_name="pca Standard Forecast")

    # As the outputs show, the forecasted values of the total 33 factors are generated using ARIMA.
    # The principal components of the macroeconomic factors are reduced from 33 to 5 through PCA, and the forecasted values of these factors are also generated using ARIMA.
