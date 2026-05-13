# manga

Angular & TypeScript + Django & Python

Search for manga panels by typing in vibes

# Features
Search
-User types in text-based search query on frontend e.g. "chibi mad expression"
-Queries the Postgres database and grabfindss the k most nearest vector embeddedings, returning their image file paths
-Backend grabs the actual images from the Cloudflare R2
-Backend gives the filepaths to the frontend

Upload
-Angular frontend takes in an image to a manga page
-Backend compresses the image by converting it into a smaller image type e.g. .avif format
-OpenCV crops the manga panel boxes
-runs the OpenCLIP embedding function
-stores the path to the file & embedding in the Cloudflare R2 storage
-Uploads the file into  or a local folder on your computer, depending on the ____ flag.

Upload-webscrape
-Angular frontend takes in a link to manga page.
-Webscraper goes onto the manga page and grabs all manga images
- THen follows the upload functionaltiy

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