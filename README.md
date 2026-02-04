🛠️ How It Works
The recommendation engine follows a specific data pipeline to ensure relevance:

User Input: Accepts book titles or authors through a Flask frontend.

Data Acquisition: Queries the Google Books API to retrieve metadata (descriptions, categories, etc.).

Data Cleaning: Processes text data to prepare it for similarity analysis.

Similarity Engine: Uses Jaccard Similarity (implemented in utils.py) to compare book attributes and find the closest matches.

Output: Returns a curated list of recommendations back to the user interface.

📁 Key Files
main.py: The core Flask application handling routes and user interaction.

utils.py / recommend.py: The "brains" of the operation. Contains logic for API calls, data cleaning, and the recommendation workflow.

notebooks/nltk_playground.ipynb: An exploratory sandbox where NLTK and NLP strategies are tested.

library.parquet: Local data storage for optimized performance during processing.

Dockerfile: Containerization settings for easy deployment.

🧪 Tech Stack & Learnings
This project served as a practical application of several data science and web development concepts:

Web Framework: Flask

Natural Language Processing: NLTK (Tokenization, cleaning)

Recommendation Systems: Content-based filtering using Jaccard Similarity.

Data Handling: Pandas and Parquet for efficient data storage.

DevOps: Docker for environment consistency.


