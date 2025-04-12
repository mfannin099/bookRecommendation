import os 
import requests
import pandas as pd
import numpy as np
# import pyarrow
# from dotenv import load_dotenv
# load_dotenv()
# API_KEY = os.getenv("API_KEY")


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



# Begin Function Definitions
def check_to_run_initial_data_load(CACHE_PATH,titles_l,authors_l, FORCE_RUN):
    if os.path.exists(CACHE_PATH)  and not FORCE_RUN:
        # print("False") # For Debugging
        return pd.read_parquet(CACHE_PATH)
        
    else:
        # print("True") # For Debugging
        create_library(titles_l, authors_l)
        
    return pd.read_parquet(CACHE_PATH)

def create_library(*args):
    df = pd.DataFrame()
    titles_l, authors_l = args

    for title, author in zip(titles_l, authors_l):

        search_term = title
        author = author
        relevance = 'relevance'

        url = f"https://www.googleapis.com/books/v1/volumes?q={search_term}+inauthor{author}&maxResults=1&orderBy={relevance}"
        book_data = pull_from_google_books(url)

        df = df.append(book_data)

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









