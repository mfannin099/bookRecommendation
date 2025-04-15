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



titles_l = [
    "Why Machines learn",
    "The Mental Game Winning the war within your mind",
    "better small talk",
    "Bullshit Jobs",
    "The Science of Self-Learning",
    "Zen Golf",
    "Netflix Powerful: Building a Culture of Freedom and Responsibility",
    "Happier Hour",
    "The Fourth Turning An American Prophecy What the cycles of history tell us about Americas nrxt Rendezvous with Destiny",
    "The Ten Day MBA",
    "Humor, Seriously",
    "How the World Ran out of Everything Inside the Global Supply Chain",
    "The Great Game of Business The Only Sensible Way to Run a Company"

] 

authors_l = [
    "Anil Ananthaswamy",
    "Darrin Donnelly",
    "Patrick King",
    "David Graeber",
    "Peter Hollins",
    "Dr Joesph Parent",
    "Patty McCord",
    "Cassie Holmes, phD",
    "William Strauss & Neil Howe",
    "Steven Silbiger",
    "Jennifer Aaker & Naomi Bagdonas",
    "Peter S. Goodman",
    "Jack Stack"

]

######################
######################
######################

# Begin Function Definitions

def read_data(data_path1, data_path2):

    if not os.path.isfile(data_path1):
        raise FileNotFoundError(f"File not found: {data_path1}")
        return None
    if not os.path.isfile(data_path2):
        raise FileNotFoundError(f"File not found: {data_path2}")
        return None

    with open(data_path1, 'r', encoding='utf-8') as file:
        authors_l = [line.strip() for line in file if line.strip()]
    with open(data_path2, 'r', encoding='utf-8') as file:
        titles_l = [line.strip() for line in file if line.strip()]

    return authors_l,titles_l


def check_to_run_initial_data_load(CACHE_PATH,data_path1,data_path2, FORCE_RUN):
    if os.path.exists(CACHE_PATH)  and not FORCE_RUN:
        # print("False") # For Debugging
        return pd.read_parquet(CACHE_PATH)
        
    else:
        # print("True") # For Debugging
        authors_l, titles_l = read_data(data_path1,data_path2)
        create_library(titles_l, authors_l)
        
    return pd.read_parquet(CACHE_PATH)


def create_library(*args):
    df = pd.DataFrame(columns=["title", "subtitle", "authors", "pulishedDate", "pageCount",
                               "categories",  "description"])
    titles_l, authors_l = args

    for title, author in zip(titles_l, authors_l):

        search_term = title
        author = author
        relevance = 'relevance'

        url = f"https://www.googleapis.com/books/v1/volumes?q={search_term}+inauthor{author}&maxResults=1&orderBy={relevance}"
        book_data = pull_from_google_books(url)

        print(book_data)

        df = pd.concat([df, book_data], ignore_index=True)

    df['full_title'] = np.where(
        df['subtitle'].notnull(),  # Check if subtitle exists
        df['title'] + " " + df['subtitle'],  # If yes
        df['title']  # If no
    )

    df.to_csv("library.csv")
    df.to_parquet("library.parquet")


def pull_from_google_books(url):

    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()

        book = []
        volume_info = data['items'][0]['volumeInfo'] 

        # print(volume_info)
        
        book.append({
            'title': volume_info.get('title'),
            'subtitle': volume_info.get('subtitle'),
            'authors': volume_info.get('authors'),
            'pulishedDate': volume_info.get('publishedDate'),
            'pageCount': volume_info.get('pageCount'),
            'categories': volume_info.get('categories'),
            'description': volume_info.get('description'),
            

        })
        df = pd.DataFrame(book)
        return df
    else:
        print("Error:", response.status_code)


def clean_data_for_tfidf(df, MATCH_SCORE, LAST_N_BOOKS,titles_l):
    # Create the score column by directly comparing row to list element at same index
    df['match_score'] = [
    fuzz.partial_ratio(row_title, list_title) 
    for row_title, list_title in zip(df['full_title'], titles_l)
    ]

    # Filtering to scores only greater than match score
    df = df[df['match_score'] >= MATCH_SCORE]

    # Error handling (if length is longer than LAST N BOOKS everything is fine) else.... just return the df
    if len(df) > LAST_N_BOOKS:
        df = df.tail(LAST_N_BOOKS)
    else:
        pass

    df['description'] = df['description'].astype(str).apply(
        lambda x: re.sub(f"[{re.escape(string.punctuation)}]", "", x)
    )

    return df


def tfidf(df, terms):
    # TF-IDF vectorization
    tfidf = TfidfVectorizer(stop_words='english')
    X = tfidf.fit_transform(df['description'])

    # Get feature names and sum TF-IDF scores across all documents
    feature_names = tfidf.get_feature_names_out()
    tfidf_scores = X.sum(axis=0).A1  # Flatten the matrix to 1D array

    top_indices = tfidf_scores.argsort()[-terms:][::-1]
    top_keywords = [feature_names[i] for i in top_indices]

    # Formating
    tfidf_search_query = " ".join(top_keywords)

    return tfidf_search_query


def get_book_recs_from_api(search_query, n):

    url = f"https://www.googleapis.com/books/v1/volumes?q={search_query}&maxResults={n}"

    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()

        return_df = pd.DataFrame()
        book = []
        for item in data.get('items', [])[:n]:
            volume_info = item.get('volumeInfo', {})

            # print(volume_info)
            
            book.append({
                'title': volume_info.get('title'),
                'subtitle': volume_info.get('subtitle'),
                'authors': volume_info.get('authors'),
                'pulishedDate': volume_info.get('publishedDate'),
                'pageCount': volume_info.get('pageCount'),
                'categories': volume_info.get('categories'),
                'description': volume_info.get('description')    

            })
            return_df = pd.DataFrame(book)
        return return_df
    else:
        print("Error:", response.status_code)
        pass










