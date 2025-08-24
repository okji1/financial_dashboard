# Backend (Flask API)

This directory contains the Flask API server that provides data to the frontend.

## Local Development

### 1. Prerequisites

- Python 3.8+
- A Supabase account and project.

### 2. Setup

1.  **Create a Supabase Table:**
    In your Supabase project, create a new table with the following properties:
    - Table Name: `kis_token`
    - Columns:
        - `id` (int8, primary key, auto-incrementing)
        - `created_at` (timestamptz, default: `now()`)
        - `access_token` (text)
        - `expires_in` (int8)

2.  **Set up Python Environment:**
    It is highly recommended to use a virtual environment.

    ```bash
    # Navigate to the backend directory
    cd financial-dashboard/backend

    # Create a virtual environment
    python3 -m venv venv

    # Activate it
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create `.env` file:**
    Create a file named `.env` in this directory by copying the example file.
    ```bash
    cp .env.example .env
    ```
    Now, open the `.env` file and fill in your actual API keys and Supabase credentials from the `api키.pdf` document.

### 3. Running the Server

Once the setup is complete, you can run the Flask development server:

```bash
flask run
```

The API will be available at `http://127.0.0.1:5000`.

## Deployment to Render

1.  **Push to GitHub:**
    Create a new repository on GitHub and push your `financial-dashboard` project to it.

2.  **Create a New Web Service on Render:**
    - Log in to Render and click "New +" -> "Web Service".
    - Connect your GitHub repository.
    - **Root Directory:** Set this to `backend`.
    - **Environment:** Choose `Python 3`.
    - **Build Command:** `pip install -r requirements.txt`
    - **Start Command:** `gunicorn app:app`

3.  **Add Environment Variables:**
    - Go to the "Environment" tab for your new service.
    - Add all the key-value pairs from your local `.env` file as environment variables.

4.  **Deploy:**
    Render will automatically build and deploy your application. Once it's live, you will get a public URL for your API.
