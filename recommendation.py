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

#Importing Utils Functions
from utils import check_to_run_initial_data_load, pull_from_google_books, create_library,clean_data_for_tfidf
from utils import tfidf, get_book_recs_from_api, create_final_recs
# from utils import titles_l # Input data
# from utils import authors_l # Input data

# Final Books DF
# Global Vars

AUTHORS_PATH = "data/authors.txt" # User input data
TITLES_PATH = "data/titles.txt" # User input data
CACHE_PATH = "library.parquet" # Path for data cache
FORCE_RUN = False

MATCH_SCORE = 70 # Fuzzy Euzzy - validate results from Google API
LAST_N_BOOKS = 10 # Number of books to use for TFIDF
TERMS_IN_SEARCH_QUERY = 10 # Number of terms to use in the search query
BOOKS_TO_RETURN = 30 # Max is 40... Per API docs


## Begin the script
final_books_df,titles_l = check_to_run_initial_data_load(CACHE_PATH, AUTHORS_PATH, TITLES_PATH, FORCE_RUN) #Checking if data pull is needed and runs if so
final_books_df = clean_data_for_tfidf(final_books_df,MATCH_SCORE,LAST_N_BOOKS,titles_l) # Cleaning the data
search_query = tfidf(df=final_books_df, terms = TERMS_IN_SEARCH_QUERY) # Returns optimized query for future recommendations
recs_from_google = get_book_recs_from_api(search_query=search_query,n=BOOKS_TO_RETURN) # Retrieving the recommendations and returns a dataframe
final = create_final_recs(recs_from_google, search_query)
print(final)


## Next steps here:

## Convert functions to classes and methods...?
## Some sort of front end for the app.... Streamlit..., want to do something different (FLASK or something else)
## Watch some flask tutorials and come back to this