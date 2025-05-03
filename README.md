### Stock Analysis/Stock Research & ML Prediction
A personal data science project to analyze stocks inputted by user. In addition, a prediction for the closing price for the next N-days can be created. Also, Streamlit app (hosted on Streamlits website... ML model doesn't work well) and Voila app are there.




### 📥 Getting Started
Clone the repository:

git clone [https://github.com/mfannin099/stock_analysis.git](https://github.com/mfannin099/bookRecommendation.git)
cd stock_analysis
Install required packages:
pip install -r requirements.txt

voila: cd notebooks, voila  voila_app.ipynb
streamlit: streamlit run app.py

### Important Files:

- app.py                      ...... Streamlit app that allows user to input stock & how many days out for ML model to predict

- stock_analysis_script.py    ...... User inputs stock, the script gives info like: EDA, lienar regression line, Monte Carlo simulation (95% confidence interval of 1 year price, probably of returns), and best/worst case scenarios for a year
- 
- notebooks/predictions.ipynb ...... notebook to test various forecasting approaches (stats, naive random, ML)

- notebooks/nke.ipynb         ...... Notebook that contains code for stock analysis (pretty decent stuff, some more technical things too)... this was the foundation for stock_analysis_script.py

- notebooks/voila_app.ipynb   ...... Web app within a notebook (Streamlit app is based off of this 

### Learnings/Practice:
- Stock analysis/ more technical things to look into
- Stats (Monte Carlo Simulations)
- Xgboost + Naive Random Walk Ensemble forecasting model 
- Voila



### Main Goals & Objectives:
- Stock analysis
- Forecast stock prices
- Look into ways other than Streamlit to make simple web apps
- Pull data from Yahoo Finance


### Improvements: 
ML Model
Streamlit app (figure out why that doesn't work hosted on Streamlits site)
