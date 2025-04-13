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
from utils import titles_l # Input data
from utils import authors_l # Input data

# Final Books DF
# Global Vars

CACHE_PATH = "library.parquet"
FORCE_RUN = False
MATCH_SCORE = 70
LAST_N_BOOKS = 10
TERMS_IN_SEARCH_QUERY = 7


## Begin the script
final_books_df = check_to_run_initial_data_load(CACHE_PATH,titles_l,authors_l, FORCE_RUN)
final_books_df = clean_data_for_tfidf(final_books_df,MATCH_SCORE,LAST_N_BOOKS,titles_l)


print(final_books_df)



## Next steps here:

## Before that.... Make seperate project (Repo) for this
## Need to really make a main.py & add api call to utils so that it is only called on the first time
## Cache the results pretty much (getting tired of waiting lol)

## Clean up full title + description to create a bag of words
## In order to create some sort of "optimal Query" to call into Google Book API
## From that Google API call... distill from that n number of returned books to get the handful that are most relevant