### Stock Analysis/Stock Research & ML Prediction
A personal data science project to analyze stocks inputted by user. In addition, a prediction for the closing price for the next N-days can be created. Also, Streamlit app (hosted on Streamlits website... ML model doesn't work well) and Voila app are there.




### 📥 Getting Started
Clone the repository:

git clone [https://github.com/mfannin099/stock_analysis.git](https://github.com/mfannin099/bookRecommendation.git)

cd bookRecommendation (Pretty sure .venv is the correct virtual enviroment I used.... has newer version of python on it)
Install required packages:
pip install -r requirements.txt

Flask: python main.py

### Important Files:

- main.py                      ...... Flask app that allows user to input books/authors.. calls the google books API, and creates recommendations

- recommend.py    ...... python file that holds all of the functions in .utils, and when called runs the workflow. That is grabs data from google books api, cleans data, creates a search query, returns search query into google api, retrieves recommendations, then returns recommendations.
  
- notebooks/nltk_playground.ipynb ...... notebook to test various natural language approaches

### Learnings/Practice:
- Flask
- Natural Language Processing
- Recommendation Systems



