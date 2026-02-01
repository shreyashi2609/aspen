# A.S.P.E.N
## Autonomous Sentry for Payment Erroneous Networks.

0. Prerequisite

Create a .env file and generate a (groq api key)[https://console.groq.com/keys]

Then put this in the .env file: `GROQ_API_KEY=YOUR_API_KEY`


1. Backend Environment Setup
Create a virtual environment to isolate the Python dependencies.

Create Virtual Environment:

Bash
python -m venv venv
Activate Environment:

Windows: venv\Scripts\activate

macOS/Linux: source venv/bin/activate

Install Dependencies:

Bash
pip install -r requirements.txt

2. Frontend Environment Setup
Install the necessary Node.js packages for the React dashboard.

Install Packages:

Bash
npm install
3. Running the Project
You will need three separate terminal instances to run the full simulation.

Start the Simulator:

Bash
python logger.py
Start the API Server:

Bash
python server.py
Start the Dashboard:

Bash
npm start
