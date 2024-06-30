import pandas as pd
from datetime import datetime
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import yfinance as yf

import math

import opstrat as op

import streamlit as st

################## 3 partie 1###########################
class dataRequest :

    def __init__(self, ticker: str, isOpt: bool, startDate=None, endDate=None):

        self.isOpt = isOpt
        self.ticker = yf.Ticker(ticker)
        self.symbol = ticker
        self.spotPrice = yf.download(ticker, period="1d")['Close'].iloc[-1]

        if self.isOpt :
            self.fileName = os.path.join('devoirOptions', 'options_data_')
            self.todayDate = datetime.today().strftime('%Y-%m-%d')
            self.calls,self.puts = self.get_option_data()
        else:
            assert startDate is not None ,"startDate doit être renseigné"
            assert endDate is not None , "endDate doit être renseigné"

            self.startDate= startDate
            self.endDate = endDate
            self.fileName = os.path.join('devoirOptions', 'data_underlying_')
            self.udlData = self.get_underlying_data(self.startDate,self.endDate)

        self.generatedFileName = self.file_name_generator()

    def delta_time_to_maturity(self, df):
        maturity = pd.to_datetime(df['Maturity'])
        df['Time to maturity'] = (maturity - datetime.strptime(self.todayDate,"%Y-%m-%d")).dt.days / 365
        return df

    def log_moneyness(self,df,optType):
        if optType == 'C' :
            df['Log_moneyness'] =  df["strike"].apply(lambda x : math.log(self.spotPrice / x) )
        else :
            df['Log_moneyness'] =  df["strike"].apply(lambda x : math.log( x / self.spotPrice ) )
        return df

    def get_underlying_data(self,startDate,endDate):
        data = self.ticker.history(start=startDate,end=endDate)['Close'].reset_index(drop = False)
        data['Date'] = data['Date'].apply(lambda x : datetime.strftime(x,'%Y-%m-%d'))

        return data


    def get_option_data(self):

        maturities = self.ticker.options

        callsList = list()
        putsList = list()

        for maturity in maturities:
            optionChain = self.ticker.option_chain(maturity)
            Calls = optionChain.calls
            Puts = optionChain.puts
            Calls['Maturity'] = maturity
            Puts['Maturity'] = maturity
            callsList.append(Calls)
            putsList.append(Puts)

        callsDf = pd.concat(callsList).reset_index(drop=True)
        putsDf = pd.concat(putsList).reset_index(drop=True)

        calls = callsDf[
            ['Maturity', 'strike', 'lastPrice', 'currency', 'impliedVolatility', 'inTheMoney', 'openInterest', 'volume',
             'contractSymbol']]
        calls['Maturity'] = pd.to_datetime(calls['Maturity'])
        calls = self.delta_time_to_maturity(calls)
        calls = self.log_moneyness(calls, 'C')

        puts = putsDf[
            ['Maturity', 'strike', 'lastPrice', 'currency', 'impliedVolatility', 'inTheMoney', 'openInterest', 'volume',
             'contractSymbol']]
        puts = self.delta_time_to_maturity(puts)
        puts = self.log_moneyness(puts, 'P')

        return calls, puts

    def file_name_generator(self):
        if self.isOpt == True :
            fileName = f"{self.fileName}{self.todayDate}.xlsx"
        else:
            fileName = f"{self.fileName}{self.symbol}.xlsx"
        return fileName

    def excel_generator(self):
        with pd.ExcelWriter(self.generatedFileName, engine="xlsxwriter") as writer:
            if self.isOpt == True :
                self.calls.to_excel(writer, sheet_name="Calls")
                self.puts.to_excel(writer, sheet_name="Puts")
            else:
                self.udlData.to_excel(writer,sheet_name="UDL")
        pass
################## 3 partie 2 ###########################
class dataFramer:
    def __init__(self,startDate:str,endDate:str,symbolUnderlying):

        self.symbol = symbolUnderlying
        self.startDate = startDate
        self.endDate = endDate
        self.fileNameOption = os.path.join('/mount/src/optionstreamapp/devoirOptions', f'options_data_')
        self.fileNameUnderlying = os.path.join('/mount/src/optionstreamapp/devoirOptions', f'data_underlying_{symbolUnderlying}')
        self.fileType= ".xlsx"

        self.missingDatesList = list()
        self.datesList = self.generate_business_dates(self.startDate,self.endDate)

        self.dataOption = self.concat_option_data(self.datesList)
        self.dataOption = self.dataOption[self.dataOption["impliedVolatility"] > 0.01]# remove data with fake implied vol values < 1 %
        self.dataUnderlying = self.excel_reader(f'{self.fileNameUnderlying}{self.fileType}')[['Date','Close']]

    def generate_business_dates(self,start_date : str, end_date: str):
        # Créer une série  dates avec seulement les jours ouvrables
        business_dates = pd.date_range(start= start_date, end=end_date, freq='B')
        # Convertir dates format 'YYYY-MM-DD' et en liste
        business_dates_list = business_dates.strftime('%Y-%m-%d').tolist()
        return business_dates_list

    def excel_reader(self,fileName : str):
        excel_file = pd.ExcelFile(fileName)
        sheet_names = excel_file.sheet_names
        df_list = []

        for sheet in sheet_names:
            df_sheet = pd.read_excel(fileName, sheet_name=sheet)
            df_sheet['sheet_name'] = sheet
            df_list.append(df_sheet)
        df = pd.concat(df_list, ignore_index=True)

        return df

    def concat_option_data (self,dateList ):

        df_list = []
        for date in dateList:
            fileName = f'{self.fileNameOption}{date}{self.fileType}'

            if os.path.isfile(fileName) == True :
                df = self.excel_reader(fileName)
                df['Date'] = date
                df_list.append(df)
            else :
                self.missingDatesList.append(date)

        df = pd.concat(df_list, ignore_index=True)
        df= df[['Maturity', 'strike', 'lastPrice', 'currency',
                 'impliedVolatility', 'inTheMoney', 'openInterest',
                 'volume','contractSymbol', 'Time to maturity',
                 'Log_moneyness', 'sheet_name','Date']]

        return df
class VolatilitySurface:
    def __init__(self, underlying, date: str,day_Range : list = None,moneyness_range :list= None):
        self.date = date

        self.data_framer = dataFramer(startDate=date, endDate=date, symbolUnderlying=underlying).dataOption
        self.filter_range = {'Time to maturity':[float(1/365),float(720/365)],"Log_moneyness":[-3,3]}
        if day_Range is not None:
            self.filter_range['Time to maturity'] = [float(x/365) for x in day_Range ]
        if moneyness_range is not None:
            self.filter_range["Log_moneyness"] = moneyness_range


    def get_filtred_data(self):
        filtered_df = self.data_framer[
            (self.data_framer['Time to maturity'].between(self.filter_range['Time to maturity'][0],self.filter_range['Time to maturity'][1]))&
            (self.data_framer["Log_moneyness"].between(self.filter_range["Log_moneyness"][0],self.filter_range["Log_moneyness"][1]))
        ]

        return filtered_df

    def plot_volatility_surface(self):

        df_options = self.get_filtred_data()

        fig = go.Figure(data=[go.Scatter3d(
            x=df_options['Log_moneyness'],
            y=df_options['Time to maturity'] * 365,
            z=df_options['impliedVolatility'],
            mode='markers',
            marker=dict(
                size=3,
                color=df_options['impliedVolatility'],
                colorscale='Rainbow',
                opacity=0.9
            ),
            surfaceaxis=2,
            surfacecolor='lightblue'
        )])


        fig.update_layout(
            title=f'Volatility Surface  {self.date}',
            scene=dict(
                xaxis_title='Log Moneyness',
                yaxis_title='Time to Maturity (days)',
                zaxis_title='Implied Volatility'
            )
        )

        return fig
class backTestCallSpread:
    def __init__(self, dfUnderlying: pd.DataFrame, dfOptions: pd.DataFrame, startDate: str, timeToMaturity: int,
                 strike1: int, strike2: int, isLong: bool):

        self.dfOptions = dfOptions
        self.dfUnderlying = dfUnderlying

        self.startDate = startDate
        self.lastDate = self.dfUnderlying['Date'].iloc[-1]

        self.optionsType = "Calls"
        self.timeTomaturity = timeToMaturity
        self.isLong = isLong

        assert strike1 <= strike2, 'strike 1 > strike2'

        self.strike1, self.strike2 = strike1, strike2

        self.optionSymbol1 = self.select_option_symbols(self.strike1)
        self.optionSymbol2 = self.select_option_symbols(self.strike2)

        self.maturityDate = str(self.get_option_info(self.optionSymbol1, 'Maturity', self.startDate)).replace(" 23:59:59","")

        self.timeTomaturityOverSample = self.get_option_info(self.optionSymbol1, 'Time to maturity', self.lastDate)

    def select_option_symbols(self, strike):
        optionsToSelectDf = self.dfOptions[
            (self.dfOptions["Date"] == self.startDate) &
            (self.dfOptions["sheet_name"] == self.optionsType)
            ]

        optionsToSelectDf['maturity_diff'] = abs(
            round(optionsToSelectDf["Time to maturity"] * 360) - self.timeTomaturity)

        closest_maturity_df = optionsToSelectDf[optionsToSelectDf['strike'] == strike]

        if closest_maturity_df.empty:
            return None

        closest_maturity_row = closest_maturity_df.loc[closest_maturity_df['maturity_diff'].idxmin()]

        optionSymbol = closest_maturity_row['contractSymbol']

        return optionSymbol

    def get_option_info(self, option_symbol, column_name, date):
        option_info = self.dfOptions[
            (self.dfOptions['Date'] == date) &
            (self.dfOptions['contractSymbol'] == option_symbol)
            ][column_name].values
        return option_info[0] if len(option_info) > 0 else None

    def get_constat_price(self):
        if self.maturityDate in self.dfUnderlying['Date'].values :
            lastUnderlyingPrice = self.dfUnderlying[self.dfUnderlying['Date'] == self.maturityDate]['Close'].values[0]
        else :
            lastUnderlyingPrice = self.dfUnderlying['Close'].iloc[-1]

        return lastUnderlyingPrice

    # backtest des donnes en dynamic
    def dynamic_backtest(self):
        dfOpt1 = self.dfOptions[['Date', 'lastPrice']][self.dfOptions['contractSymbol'] == self.optionSymbol1]
        dfOpt2 = self.dfOptions[['Date', 'lastPrice']][self.dfOptions['contractSymbol'] == self.optionSymbol2]

        if self.isLong:
            dfOpt1['PnL_opt1'] = dfOpt1['lastPrice'].diff().fillna(0)
            dfOpt2['PnL_opt2'] = dfOpt2['lastPrice'].diff().fillna(0) * (-1)
        else:
            dfOpt1['PnL_opt1'] = dfOpt1['lastPrice'].diff().fillna(0) * (-1)
            dfOpt2['PnL_opt2'] = dfOpt2['lastPrice'].diff().fillna(0)

        df = pd.merge(dfOpt1, dfOpt2, on='Date', suffixes=('_opt1', '_opt2'))
        df['PnL'] = df['PnL_opt1'] + df['PnL_opt2']

        df['Cumulative_PnL_opt1'] = df['PnL_opt1'].cumsum()
        df['Cumulative_PnL_opt2'] = df['PnL_opt2'].cumsum()
        df['Cumulative_PnL'] = df['PnL'].cumsum()

        return df
    # backtest des donnes en dynamic en payoffs
    def intrinsec_backtest(self):
        last_underlying_price = self.get_constat_price()

        intrinsic_value_opt1 = max(last_underlying_price - self.strike1, 0)
        intrinsic_value_opt2 = max(last_underlying_price - self.strike2, 0)

        premiumOpt1 = self.get_option_info(self.optionSymbol1, 'lastPrice', self.startDate)
        premiumOpt2 = self.get_option_info(self.optionSymbol2, 'lastPrice', self.startDate)

        if self.isLong:
            pnl_opt1 = intrinsic_value_opt1 - premiumOpt1
            pnl_opt2 =  premiumOpt2 - intrinsic_value_opt2
        else:
            pnl_opt1 = premiumOpt1 - intrinsic_value_opt1
            pnl_opt2 = intrinsic_value_opt2 - premiumOpt2

        total_pnl = pnl_opt1 + pnl_opt2

        return {
            'Total_PnL': total_pnl,
            'PnL_Opt1': pnl_opt1,
            'PnL_Opt2': pnl_opt2,
            'Last_Underlying_Price': last_underlying_price
        }
class OptionPayoff:
    def __init__(self):
        pass

    def plot_payoff(self, spot_price, legs):
        positions = []
        strikes = []

        for leg in legs:
            position = {
                "op_type": leg["option_type"],
                "strike": leg["strike"],
                "tr_type": leg["position"],
                "op_pr": leg["premium"]
            }
            positions.append(position)
            strikes.append(leg["strike"])


        max_strike = max(strikes)
        min_strike = min(strikes)
        range_strikes = int(abs(max_strike - min_strike) * 1.5)
        range_spot = int(max(abs(max_strike - spot_price), abs(min_strike - spot_price)) * 1.5)
        spot_range = max(range_strikes, range_spot)

        if len(positions) == 1:
            fig = op.single_plotter(
                spot=spot_price,
                strike=positions[0]['strike'],
                op_type=positions[0]['op_type'],
                tr_type=positions[0]['tr_type'],
                op_pr=positions[0]['op_pr']
            )
        else:
            fig = op.multi_plotter(
                spot=spot_price,
                op_list=positions,
                spot_range=spot_range
            )

        return fig
#from sklearn.ensemble import RandomForestClassifier

class ModelRandomForest:
    def __init__(self, startDate, endDate, udl, nEstimator, test_size):
        self.startDate = startDate
        self.endDate = endDate
        self.udl = udl
        self.test_size = test_size
        self.minTimeToMaturity = 14
        self.x_features = ["Log_moneyness", "Time to maturity", 'impliedVolatility']
        self.model = RandomForestClassifier(n_estimators=nEstimator, n_jobs=-1)

    def prepare_data(self):
        data = dataFramer(self.startDate, self.endDate, self.udl)
        allDates = [date for date in data.datesList if date not in data.missingDatesList]

        trainingSize = int(len(allDates) * self.test_size)
        trainingDate = allDates[:trainingSize]

        trainingSampleSymbol = data.dataOption['contractSymbol'][
            (data.dataOption["Date"] == trainingDate[-1]) &
            (data.dataOption['Time to maturity'] * 360 > self.minTimeToMaturity)
        ]
        self.trainingSample = data.dataOption[
            (data.dataOption['contractSymbol'].isin(trainingSampleSymbol)) &
            (data.dataOption['Date'].isin(trainingDate))]

        testingDate = allDates[trainingSize:]
        testingSampleSymbol = data.dataOption['contractSymbol'][
            (data.dataOption["Date"] == testingDate[-1]) &
            (data.dataOption['Time to maturity'] * 360 > self.minTimeToMaturity)
        ]
        self.testingSample = data.dataOption[
            (data.dataOption['contractSymbol'].isin(testingSampleSymbol)) &
            (data.dataOption['Date'].isin(testingDate))]

    def prepare_Y_toPredict(self, sample: pd.DataFrame):
        for symbol in sample["contractSymbol"].drop_duplicates():
            sample.loc[sample["contractSymbol"] == symbol, 'Y_toPredict'] = (
                sample[sample["contractSymbol"] == symbol]["lastPrice"].diff()
                .apply(lambda PnL: 1 if PnL > 0 else -1 if PnL < 0 else None)
            )
        sample.dropna(subset=['Y_toPredict'], inplace=True)
        return sample

    def train_model(self):
        sampleToTrain = self.prepare_Y_toPredict(self.trainingSample)
        X_train = sampleToTrain[self.x_features].round(3)
        y_train = sampleToTrain['Y_toPredict'].dropna().astype(int)
        X_train = X_train.loc[y_train.index]
        self.model.fit(X_train, y_train)

    def model_predictor(self):
        sampleToTest = self.prepare_Y_toPredict(self.testingSample)
        X_test = sampleToTest[self.x_features].round(3)
        predictions = self.model.predict(X_test)
        return predictions

    def evaluate_model(self):
        self.testingSample = self.prepare_Y_toPredict(self.testingSample)
        X_test = self.testingSample[self.x_features].round(3)
        y_true = self.testingSample['Y_toPredict'].astype(int)

        predictions = self.model.predict(X_test)
        self.testingSample['Y_prediction'] = predictions

        accuracy = accuracy_score(y_true, predictions)
        precision = precision_score(y_true, predictions, average='macro')
        recall = recall_score(y_true, predictions, average='macro')

        return {
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall
        }

    def plot_predictions(self):

        self.testingSample['Prediction Accuracy'] = (
                self.testingSample['Y_toPredict'] == self.testingSample['Y_prediction']
        )

        fig = px.bar(
            self.testingSample,
            x='Y_toPredict',
            y='Y_prediction',
            color='Prediction Accuracy',
            labels={
                'Y_toPredict': 'Actual',
                'Y_prediction': 'Predicted',
                'Prediction Accuracy': 'Prediction Correct'
            },
            opacity=0.6,
            color_discrete_map={True: 'blue', False: 'red'}
        )
        self.prediction_fig = fig



    def plot_feature_importance(self):
        importance = pd.DataFrame({
            'feature': self.x_features,
            'value': self.model.feature_importances_
        }).sort_values(by='value', ascending=False)

        fig = px.bar(
            importance,
            x='value',
            y='feature',
            orientation='h',
            color = 'feature'
        )
        self.importance_fig = fig


class StreamlitApp:
    def __init__(self):
        #eviter d'afficher un message d'erreur
        st.set_option('deprecation.showPyplotGlobalUse', False)

        self.pages = {
            "Home": self.home_page,
            "Data Request": self.data_request_page,
            "Payoff Strategy": self.payoff_strategy_page,
            "Volatility Surface": self.volatility_surface_page,
            "Backtesting": self.backtesting_page,
            "Model" : self.model_page
        }

    def run(self):
        st.sidebar.title("Navigation")
        page = st.sidebar.radio("Go to", list(self.pages.keys()))
        self.pages[page]()

    def home_page(self):
        st.title("Option Analysis App")
        st.write("available widgets Data Request,Payoff Strategy,Volatility Surface,Volatility Surface,Backtesting")

    def data_request_page(self):
        st.title("Data Request")
        st.write("Request options or underlying data.")
        ticker = st.text_input("Ticker Symbol", "^SPX")
        isOpt = st.radio("Is an Option Data Request?", (True, False))

        if not isOpt:
            start_date = st.date_input("Start Date", datetime(2024, 4, 15))
            end_date = st.date_input("End Date", datetime(2024, 6, 5))

        if st.button("Request and Display Data"):
            if isOpt:
                data = dataRequest(ticker, isOpt)
                st.write("Call Options Data:")
                st.dataframe(data.calls)
                st.write("Put options Data:")
                st.dataframe(data.puts)
            else:
                data = dataRequest(ticker, isOpt, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                st.write("Underlying Data:")
                st.dataframe(data.udlData)

        #if st.button("Insert Data into Excel"):
            #if isOpt:
                #data = dataRequest(ticker, isOpt)
                #data.excel_generator()
                #st.success("Excel File Correctly Loaded.")
            #else:
                #data = dataRequest(ticker, isOpt, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                #data.excel_generator()
                #st.success("Excel File Correctly Loaded.")

    def backtesting_page(self):
        st.title(" Backtesting")

        st.write("Perform backtesting on Call-Spread Strategy ")
        ticker = st.text_input("Ticker Symbol", "^SPX")
        start_date = st.date_input("Start Date", datetime(2024, 4, 15))
        end_date = st.date_input("End Date", datetime(2024, 6, 29))
        time_to_maturity = st.number_input("Time to Maturity (days)", min_value=1, value=100)
        strike1 = st.number_input("Strike 1", min_value=5, value=4500,step=5)
        strike2 = st.number_input("Strike 2", min_value=5, value=5000,step=5)
        is_long = st.radio("Is Long Position?", (True, False))

        if st.button("Run Backtest"):

            data_fr = dataFramer(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), ticker)
            backtest = backTestCallSpread(data_fr.dataUnderlying, data_fr.dataOption, start_date.strftime('%Y-%m-%d'),
                                          time_to_maturity, strike1, strike2, is_long)

            options_info = pd.DataFrame({
                "Option": ["Option 1", "Option 2"],
                "Symbol": [backtest.optionSymbol1, backtest.optionSymbol2],
                'Implied Volatility': [
                    backtest.get_option_info(backtest.optionSymbol1, 'impliedVolatility', backtest.startDate),
                    backtest.get_option_info(backtest.optionSymbol2, 'impliedVolatility', backtest.startDate)
                ],
                'Strike': [
                    backtest.get_option_info(backtest.optionSymbol1, 'strike', backtest.startDate),
                    backtest.get_option_info(backtest.optionSymbol2, 'strike', backtest.startDate)
                ],
                'Maturity': [
                    backtest.get_option_info(backtest.optionSymbol1, 'Maturity', backtest.startDate),
                    backtest.get_option_info(backtest.optionSymbol2, 'Maturity', backtest.startDate)
                ]
            })

            st.write("Options Info:")
            st.dataframe(options_info)

            results = backtest.dynamic_backtest()
            st.write("Backtest Results:")
            st.dataframe(results)
            st.line_chart(results[['Cumulative_PnL']])

            # Intrinsic Backtest
            intrinsic_results = backtest.intrinsec_backtest()
            intrinsic_df = pd.DataFrame([intrinsic_results])
            st.write("Intrinsic Backtest Results:")
            st.dataframe(intrinsic_df)

    def payoff_strategy_page(self):
        st.title("Payoff Strategy")
        st.write("Plot the payoff of an Option Strategy.")
        spot_price = st.number_input("Spot Price", min_value=1, value=100)
        num_legs = st.number_input("Number of Legs", min_value=1, value=1)

        legs = []
        for i in range(num_legs):
            st.subheader(f"Leg {i + 1}")
            strike = st.number_input(f"Strike Price {i + 1}", min_value=1, key=f"strike_{i}")
            premium = st.number_input(f"Premium {i + 1}", min_value=0.0, format="%.2f", key=f"premium_{i}")
            quantity = st.number_input(f"Quantity {i + 1}", min_value=1, value=1, key=f"quantity_{i}")
            position = st.selectbox(f"Position {i + 1}", options=["long", "short"], index=0, key=f"position_{i}")
            option_type = st.selectbox(f"Option Type {i + 1}", options=["call", "put"], index=0, key=f"option_type_{i}")

            legs.append({
                "strike": strike,
                "premium": premium,
                "quantity": quantity,
                "position": 'b' if position == 'long' else 's',
                "option_type": 'c' if option_type == 'call' else 'p'
            })

        if legs:
            summary_df = pd.DataFrame(legs)
            summary_df["premium"] = summary_df["premium"].map(lambda x: f"${x:.2f}")
            st.write("Summary of Entered Data:")
            st.dataframe(summary_df)

        if st.button("Plot Payoff"):
            option_payoff = OptionPayoff()
            fig = option_payoff.plot_payoff(spot_price, legs)
            st.pyplot(fig)

    def volatility_surface_page(self):
        st.title("Volatility Surface S&P 500 (^SPX) :")
        underlying = "^SPX"
        date = st.date_input("Date",datetime(2024, 6, 5))
        min_maturity ,max_maturity = st.slider("Select days to Maturity Range ",min_value=1,max_value=720,value=(7,360))
        min_moneyness,max_moneyness = st.slider("Select moneyness Range",min_value= -1.0,max_value= 1.0,value=(-0.2,0.2))
        current_directory = os.getcwd()

        if st.button("Plot Volatility Surface"):
            try:
                surface = VolatilitySurface(underlying, date.strftime('%Y-%m-%d'),[min_maturity,max_maturity],[min_moneyness,max_moneyness])
                fig = surface.plot_volatility_surface()
                st.plotly_chart(fig)
            except:
                st.write("No Data available please try an other date ")
    def model_page (self):
        st.title("Bonus RandomForest Model")
        st.write("decision factors implied Vol / log moneyness / time to maturity")
        ticker = st.text_input("Ticker Symbol", "^SPX")
        start_date = st.date_input("Start Date", datetime(2024, 4, 15))
        end_date = st.date_input("End Date", datetime(2024, 6, 29))
        number_of_threes = st.slider("select estimators number (Threes)",min_value=10,max_value = 100,value=50)
        test_size  = st.slider("select Training Proportion",min_value=0.5,max_value=0.9,value=0.7)
        MDL = ModelRandomForest(startDate=start_date, endDate=end_date, udl=ticker, nEstimator=number_of_threes,
                                test_size=test_size)

        if st.button('Run Model'):
            MDL.prepare_data()
            MDL.train_model()
            MDL.evaluate_model()
            st.write("Training Sample Results:")
            st.dataframe(MDL.trainingSample)
            st.success("Model Trained")

            st.write("Testing Sample Results:")
            st.dataframe(MDL.testingSample)
            st.success("Model tested ")

            MDL.plot_predictions()
            MDL.plot_feature_importance()

            st.title("Model Results:")
            st.write(pd.DataFrame([MDL.evaluate_model()]))
            st.write("Prediction Plot:")
            st.plotly_chart(MDL.prediction_fig)

            st.write("Feature Importance Plot:")
            st.plotly_chart(MDL.importance_fig)
