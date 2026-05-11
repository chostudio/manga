# manga

Angular & TypeScript + Django & Python

Search for manga panels by typing in vibes

# Features
Search
User types in text-based search query on frontend e.g. "chibi mad expression"
Queries the Postgres database and returns the k most nearest vector embeddedings & image file paths
Backend uses the filepaths to grab the actual images and return them to the frontend

Upload
Angular frontend takes in a link to manga page.
Django
Webscraper goes onto the manga page and grabs all manga images
compresses the image by converting it into a smaller image type e.g. .avif format
OpenCV crops the manga panel boxes
runs the embedding function
stores the path to the file & embedding in the Postgres database
Uploads the file into  or a local folder on your computer, depending on the ____ flag.



# set up
frontend

cd frontend

nvm use 22

"Now using node v22.14.0 (npm v10.9.2)"

ng serve --open
(will take a couple seconds to build then run on:)
http://localhost:4200/

backend

cd backend

source .venv/bin/activate

is it pip install -r
requirements.txt

python3 manage.py runserver