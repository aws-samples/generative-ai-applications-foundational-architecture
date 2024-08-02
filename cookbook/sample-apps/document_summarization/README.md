Document Summarization is a simple streamlit application to summarize a file. The application provides summaries for each page and also a summary of summaries.

1. Make sure you have configured a virtual environment.

```bash
python -m venv venv
source venv/bin/active
pip install -r reqs.txt
```

2. Create the following environment variables. Please get these values from your platform adminstrator.
export COGNITO_CLIENT_ID='' 
export COGNITO_CLIENT_SECRET='' 
export COGNITO_USER_POOL_ID='' 
export COGNITO_REGION='' 
export COGNITO_DOMAIN='' 
export PLATFORM_API_URL=''

3. Run the streamlit app
streamlit run app.py