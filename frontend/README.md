# Frontend (Next.js)

This directory contains the Next.js frontend that displays the data from the Flask API.

## Local Development

### 1. Prerequisites

- Node.js 18+
- npm

### 2. Setup

1.  **Navigate to the frontend directory:**
    ```bash
    cd financial-dashboard/frontend
    ```

2.  **Install Dependencies:**
    ```bash
    npm install
    ```

### 3. Running the Development Server

First, make sure your backend Flask server is running.

Then, run the Next.js development server:

```bash
npm run dev
```

The application will be available at `http://localhost:3000`.

**Note:** The frontend components currently point to the local backend API at `http://127.0.0.1:5000`. If you deploy the backend and want to test with the live API, you will need to change the fetch URLs in `components/GoldPremium.tsx` and `components/InvestmentStrategy.tsx`.

## Deployment to Vercel

1.  **Push to GitHub:**
    Make sure your project (including the `frontend` directory) is pushed to your GitHub repository.

2.  **Create a New Project on Vercel:**
    - Log in to Vercel and click "Add New..." -> "Project".
    - Import your GitHub repository.
    - **Root Directory:** When prompted, set the root directory to `frontend`.
    - Vercel will automatically detect that it is a Next.js project and configure the build settings.

3.  **Deploy:**
    Click "Deploy". Vercel will build and deploy your frontend. You will get a public URL for your live website.