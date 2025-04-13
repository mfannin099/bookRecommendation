import os 
import requests
# from dotenv import load_dotenv
# load_dotenv()
# API_KEY = os.getenv("API_KEY")
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
import re 
import string
from thefuzz import fuzz, process

##Importing Utils Functions
from utils import check_to_run_initial_data_load, pull_from_google_books, create_library,clean_data_for_tfidf
from utils import tfidf, get_book_recs_from_api
from utils import titles_l # Input data
from utils import authors_l # Input data

# Final Books DF
# Global Vars

CACHE_PATH = "library.parquet"
FORCE_RUN = False
MATCH_SCORE = 70
LAST_N_BOOKS = 10
TERMS_IN_SEARCH_QUERY = 7
BOOKS_TO_RETURN = 30 # Max is 40... Per API docs


## Begin the script
final_books_df = check_to_run_initial_data_load(CACHE_PATH,titles_l,authors_l, FORCE_RUN) #Checking if data pull is needed and runs if so
final_books_df = clean_data_for_tfidf(final_books_df,MATCH_SCORE,LAST_N_BOOKS,titles_l) # Cleaning the data
search_query = tfidf(df=final_books_df, terms = TERMS_IN_SEARCH_QUERY) # Returns optimized query for future recommendations
recs_from_google = get_book_recs_from_api(search_query=search_query,n=BOOKS_TO_RETURN) # Retrieving the recommendations and returns a dataframe

print(recs_from_google)


## Next steps here:

## need some sort of metric to determine the top n... recs from google api
## Could use the fuzzy wuzzy package, cosine similarity, etc. (THose come to top of mind)
## Some sort of front end for the app.... Streamlit..., want to do something different (FLASK or something else)