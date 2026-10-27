# Cell audit: database vs raw Fed files

- facts printed in raw files: 51,160
- facts printed by more than one Fed file: 10,966; of those, printed digits differ (within the coarser file's rounding, checked below): 1,558
- rows in database (actuals + scenario_paths): 51,160
- missing from database: 0; extra in database: 0
- value matches most precise printed value bit-for-bit: 51,160; equal within 1e-09 only: 0
- first projected quarter derived from data (combined-table vintages): {'2012': '2011Q4', '2013': '2012Q4', '2014': '2013Q4', '2015': '2014Q4', '2016': '2016Q1'}

## Unpublished (non-numeric) cells by file

- 2013/historical.xlsx: '' x 449

Unpublished cells by variable (first-last quarter, count):

- 2013/historical.xlsx devasia_inflation: 1976Q1-1996Q1 (81)
- 2013/historical.xlsx devasia_real_gdp_growth: 1976Q1-1996Q2 (82)
- 2013/historical.xlsx devasia_usd_exchange_rate: 1976Q1-1996Q1 (81)
- 2013/historical.xlsx euro_inflation: 1976Q1-1990Q1 (57)
- 2013/historical.xlsx euro_usd_exchange_rate: 1976Q1-1998Q4 (92)
- 2013/historical.xlsx vix: 1976Q1-1989Q4 (56)

## The Fed's own 2011 summary table (Table 1) vs the stored stress path

- unemployment_rate level_q4 2011: database 11.000, Fed Table 1 11.0 (tolerance 0.050) -> ok
- unemployment_rate level_q4 2012: database 10.600, Fed Table 1 10.6 (tolerance 0.050) -> ok
- unemployment_rate level_q4 2013: database 9.600, Fed Table 1 9.6 (tolerance 0.050) -> ok
- real_gdp_growth growth_q4q4 2011: database -1.455, Fed Table 1 -1.5 (tolerance 0.081) -> ok
- real_gdp_growth growth_q4q4 2012: database 2.398, Fed Table 1 2.4 (tolerance 0.081) -> ok
- real_gdp_growth growth_q4q4 2013: database 3.404, Fed Table 1 3.4 (tolerance 0.081) -> ok
- house_price_index level_q4q4 2011: database -5.714, Fed Table 1 -6.2 (tolerance 0.744) -> ok
- house_price_index level_q4q4 2012: database -4.545, Fed Table 1 -4.1 (tolerance 0.790) -> ok
- house_price_index level_q4q4 2013: database 3.175, Fed Table 1 2.7 (tolerance 0.856) -> ok
- dow_jones_total_stock_market_index level_q4q4 2011: database -27.782, Fed Table 1 -27.8 (tolerance 0.057) -> ok
- dow_jones_total_stock_market_index level_q4q4 2012: database 36.875, Fed Table 1 36.9 (tolerance 0.064) -> ok
- dow_jones_total_stock_market_index level_q4q4 2013: database 15.859, Fed Table 1 15.9 (tolerance 0.059) -> ok

## Problems

- none
