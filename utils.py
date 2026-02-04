import os 
import requests
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import jaccard_score
import re 
import string
from thefuzz import fuzz, process


# Begin Function Definitions

def check_to_run_initial_data_load(CACHE_PATH,data_path1,data_path2, FORCE_RUN):
    if os.path.exists(CACHE_PATH)  and not FORCE_RUN:
        # print("False") # For Debugging
        authors_l, titles_l = read_data(data_path1,data_path2)
        return pd.read_parquet(CACHE_PATH), titles_l
        
    else: # Typically this will be done
        # print("True") # For Debugging
        authors_l, titles_l = read_data(data_path1,data_path2)
        create_library(titles_l, authors_l)
        
    return pd.read_parquet(CACHE_PATH), titles_l


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

        return self.authors_list, self.titles_list

    def fetch_book_from_google(self, title, author):
        """Fetch book data from Google Books API."""
        time.sleep(1)
        url = f"https://www.googleapis.com/books/v1/volumes?q={title}+inauthor:{author}&key={API_KEY}&maxResults=1"
        
        try:
            response = requests.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'items' in data and len(data['items']) > 0:
                    volume_info = data['items'][0]['volumeInfo']
                    
                    book_data = {
                        'title': volume_info.get('title'),
                        'subtitle': volume_info.get('subtitle'),
                        'authors': volume_info.get('authors'),
                        'publishedDate': volume_info.get('publishedDate'),
                        'pageCount': volume_info.get('pageCount'),
                        'categories': volume_info.get('categories'),
                        'description': volume_info.get('description'),
                    }
                    
                    return pd.DataFrame([book_data])
            else:
                print(f"Error fetching book: {response.status_code}")
                
        except Exception as e:
            print(f"Exception while fetching book: {e}")
        
        return pd.DataFrame()

    def build_library(self):
        """Build library from input titles and authors using Google Books API."""
        df = pd.DataFrame(columns=["title", "subtitle", "authors", "publishedDate", 
                                "pageCount", "categories", "description"])
        
        for title, author in zip(self.titles_list, self.authors_list):
            print(title)
            book_data = self.fetch_book_from_google(title, author)
            df = pd.concat([df, book_data], ignore_index=True)
        
        # Create full_title column
        df['full_title'] = np.where(
            df['subtitle'].notnull(),
            df['title'] + " " + df['subtitle'],
            df['title']
        )
        
        # Save to cache
        df.to_parquet(self.cache_path)
        self.library_df = df
        
        return df

    def load_or_build_library(self):
        """Load library from cache or build it if needed."""
        self.read_data()
        
        if os.path.exists(self.cache_path) and not self.force_run:
            self.library_df = pd.read_parquet(self.cache_path)
        else:
            self.library_df = self.build_library()
        
        return self.library_df
    
    def clean_and_filter_library(self):
        """Clean library data and filter based on match scores."""
        df = self.library_df.copy()
        
        # Calculate fuzzy match scores
        df['match_score'] = [
            fuzz.partial_ratio(row_title, list_title)
            for row_title, list_title in zip(df['full_title'], self.titles_list)
        ]
        
        # Filter and select last N books
        if len(df) > self.last_n_books:
            df = df[df['match_score'] >= self.match_score]
            df = df.tail(self.last_n_books)
        
        # Clean descriptions for TF-IDF
        df['description'] = df['description'].astype(str).apply(
            lambda x: re.sub(f"[{re.escape(string.punctuation)}]", "", x)
        )
        
        return df
    
    def generate_search_query(self, df):
        """Generate optimized search query using TF-IDF."""
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(df['description'])
        
        # Get feature names and sum TF-IDF scores
        feature_names = vectorizer.get_feature_names_out()
        tfidf_scores = tfidf_matrix.sum(axis=0).A1
        
        # Get top terms
        top_indices = tfidf_scores.argsort()[-self.terms_in_search_query:][::-1]
        top_keywords = [feature_names[i] for i in top_indices]
        
        search_query = " ".join(top_keywords)
        return search_query
    
    def fetch_recommendations(self, search_query):
        """Fetch book recommendations from Google Books API."""
        url = f"https://www.googleapis.com/books/v1/volumes?q={search_query}&key={API_KEY}&maxResults={self.books_to_return}"
        
        try:
            response = requests.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                books = []
                for item in data.get('items', [])[:self.books_to_return]:
                    volume_info = item.get('volumeInfo', {})
                    
                    books.append({
                        'title': volume_info.get('title'),
                        'subtitle': volume_info.get('subtitle'),
                        'authors': volume_info.get('authors'),
                        'publishedDate': volume_info.get('publishedDate'),
                        'pageCount': volume_info.get('pageCount'),
                        'categories': volume_info.get('categories'),
                        'description': volume_info.get('description')
                    })
                
                return pd.DataFrame(books)
            else:
                print(f"Error fetching recommendations: {response.status_code}")
                
        except Exception as e:
            print(f"Exception while fetching recommendations: {e}")
        
        return pd.DataFrame()
    
    def rank_by_jaccard_similarity(self, df, search_query):
        """Rank recommendations using Jaccard similarity."""
        search_query_set = set(search_query.lower().split())
        
        def calculate_jaccard(description):
            description_set = set(str(description).lower().split())
            intersection = len(search_query_set.intersection(description_set))
            union = len(search_query_set.union(description_set))
            return intersection / union if union != 0 else 0
        
        df['jaccard_similarity'] = df['description'].apply(calculate_jaccard)
        df = df.sort_values(by='jaccard_similarity', ascending=False)
        
        # Format authors column
        df['authors'] = df['authors'].apply(
            lambda x: ', '.join(x) if isinstance(x, list) else str(x)
        )
        
        return df[['title', 'subtitle', 'authors']].head(10)
    
    def get_recommendations(self):
        """Main method to run the complete recommendation pipeline."""
        # Load or build library
        self.load_or_build_library()
        
        # Clean and filter data
        cleaned_df = self.clean_and_filter_library()
        
        # Generate search query using TF-IDF
        search_query = self.generate_search_query(cleaned_df)
        
        # Fetch recommendations from API
        recommendations_df = self.fetch_recommendations(search_query)
        
        # Rank and return final recommendations
        final_recommendations = self.rank_by_jaccard_similarity(
            recommendations_df, search_query
        )
        
        return final_recommendations