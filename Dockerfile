# Use official Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy the rest of the code
COPY . /main/

# Expose the port Flask runs on
EXPOSE 5000

# Run the app using Gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]