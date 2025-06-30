# Ferry Ticket Availability Checker

This application allows users to check ferry ticket availability for Praamid.ee routes by querying their online API. It consists of a Python Flask backend that acts as a proxy and a simple HTML/JS/CSS frontend.

## Features

- Select ferry direction (e.g., Heltermaa-Rohuküla, Kuivastu-Virtsu, etc.).
- Choose a departure date.
- View available trips for the selected date and direction, focusing on car (`sv`) availability.
- Provides a direct link to the Praamid.ee booking page for available trips.
- Requires a manual Bearer token for accessing the Praamid.ee API.

## Project Structure

```
.
├── backend/
│   ├── app.py          # Flask backend application
│   └── requirements.txt  # Python dependencies
├── frontend/
│   ├── index.html      # Main HTML page
│   ├── script.js       # Frontend JavaScript logic
│   └── style.css       # CSS styles
└── README.md           # This file
```

## Setup and Running

### Prerequisites

- Python 3.7+
- `pip` (Python package installer)
- A web browser

### Backend Setup

1.  **Navigate to the `backend` directory:**
    ```bash
    cd backend
    ```

2.  **Create a Python virtual environment (recommended):**
    ```bash
    python -m venv venv
    ```

3.  **Activate the virtual environment:**
    *   On macOS and Linux:
        ```bash
        source venv/bin/activate
        ```
    *   On Windows:
        ```bash
        .\venv\Scripts\activate
        ```

4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Run the Flask backend server:**
    ```bash
    python app.py
    ```
    The backend server will typically start on `http://localhost:8080`.

### Frontend Setup

1.  **Navigate to the `frontend` directory (in a separate terminal if your backend is running):**
    ```bash
    cd frontend
    ```

2.  **Serve the `index.html` file.** There are several ways to do this for local development:
    *   **Using Python's HTTP Server (simple):**
        ```bash
        python -m http.server 8000
        ```
        Then open `http://localhost:8000` in your web browser. (You can use any other available port).
    *   **Using a Live Server extension in your code editor** (e.g., "Live Server" in VS Code). Right-click on `index.html` and choose "Open with Live Server".

### Obtaining the Praamid.ee Bearer Token

This application requires a valid `Bearer` token from an active Praamid.ee session to fetch schedule data. You need to obtain this token manually:

1.  Open [https://www.praamid.ee](https://www.praamid.ee) in your web browser.
2.  Log in to your Praamid.ee account.
3.  Open your browser's Developer Tools (usually by pressing F12 or right-clicking on the page and selecting "Inspect").
4.  Go to the **Network** tab within the Developer Tools.
5.  In the filter bar of the Network tab, select **"Fetch/XHR"** to only show API requests.
6.  On the Praamid.ee page, perform an action that loads schedule data (e.g., select a route and a date).
7.  Look for a request in the Network tab list that goes to an endpoint like `/online/events?...`. Click on this request.
8.  A details pane will open. Look for the **Headers** section (it might be labeled "Request Headers").
9.  Find the `Authorization` header. Its value will look like `Bearer eyJhbGciOiJSUzI1NiIsI...` (a long string of characters).
10. **Copy the entire value**, including the word "Bearer " and the space after it.
11. Paste this token into the "Authorization Token (Bearer)" field in the Ferry Ticket Availability Checker web application.

**Note:** This token is temporary and will expire. If the application stops working or shows authorization errors, you will likely need to obtain a new token.

## How to Use

1.  Ensure both the backend and frontend servers are running.
2.  Open the frontend URL in your browser (e.g., `http://localhost:8000`).
3.  Paste your obtained Praamid.ee Bearer token into the designated field.
4.  Select the desired ferry direction.
5.  Choose a departure date.
6.  Click the "Get Schedule" button.
7.  The application will display the schedule, highlighting trips with available car spots.
8.  For available trips, a "Book on Praamid.ee" button will appear, linking directly to the booking page for that specific trip.

## Disclaimer

This tool interacts with the Praamid.ee website by proxying API requests. Its functionality depends on the current structure and an active session token from Praamid.ee. Changes to the Praamid.ee website or API may break this tool. Use responsibly. This tool is not affiliated with or endorsed by Praamid.ee / TS Laevad OÜ.