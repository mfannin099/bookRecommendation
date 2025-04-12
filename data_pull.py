import os 
import requests
# from dotenv import load_dotenv
# load_dotenv()
# API_KEY = os.getenv("API_KEY")
import pandas as pd
import numpy as np


from thefuzz import fuzz, process
##Importing Utils Functions
from utils import pull_from_google_books
from utils import titles_l # Input data
from utils import authors_l # Input data

# Final Books DF
# Global Vars
final_books_df = pd.DataFrame()
match_score = 70  # Could need to be adjusted (Looks right based on data that I have already)

# Start Pulling Data

for title, author in zip(titles_l, authors_l):

    search_term = title
    author = author
    relevance = 'relevance'

    url = f"https://www.googleapis.com/books/v1/volumes?q={search_term}+inauthor{author}&maxResults=1&orderBy={relevance}"
    book_data = pull_from_google_books(url)

    final_books_df = final_books_df.append(book_data)

final_books_df['full_title'] = np.where(
    final_books_df['subtitle'].notnull(),  # Check if subtitle exists
    final_books_df['title'] + " " + final_books_df['subtitle'],  # If yes
    final_books_df['title']  # If no
)
print(final_books_df)


# Create the score column by directly comparing row to list element at same index
final_books_df['match_score'] = [
    fuzz.partial_ratio(row_title, list_title) 
    for row_title, list_title in zip(final_books_df['full_title'], titles_l)
]

final_books_df = final_books_df[final_books_df['match_score'] >= match_score]
print(final_books_df)



## Next steps here:

## Before that.... Make seperate project (Repo) for this
## Need to really make a main.py & add api call to utils so that it is only called on the first time
## Cache the results pretty much (getting tired of waiting lol)

## Clean up full title + description to create a bag of words
## In order to create some sort of "optimal Query" to call into Google Book API
## From that Google API call... distill from that n number of returned books to get the handful that are most relevant