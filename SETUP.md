# Setup Guide

## Prerequisites

1. **Node.js** (v20 or higher)
   ```bash
   node --version
   ```

2. **PostgreSQL** (v14 or higher)
   ```bash
   psql --version
   ```

3. **npm** or **yarn**

## Step-by-Step Setup

### 1. Database Setup

```bash
# Create PostgreSQL database
createdb supply_chain

# Or using psql:
psql -U postgres
CREATE DATABASE supply_chain;
\q
```

### 2. Backend Setup

```bash
cd backend

# Install dependencies
yarn install

# Copy environment file
cp .env.example .env

# Edit .env file with your configuration:
# - Database credentials (DB_HOST, DB_PORT, DB_USERNAME, DB_PASSWORD, DB_NAME)
# - ANTHROPIC_API_KEY (required for AI analysis)
# - Optional: WEATHER_API_KEY, NEWS_API_KEY for real data sources

# Start backend (will auto-create tables)
yarn start:dev
```

The backend should start on `http://localhost:3001`

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
yarn install

# Copy environment file
cp .env.example .env

# Edit .env file:
# NEXT_PUBLIC_API_URL=http://localhost:3001

# Start frontend
yarn dev
```

The frontend should start on `http://localhost:3000`

### 4. Verify Setup

1. Open `http://localhost:3000` in your browser
2. You should see the dashboard with agent status
3. Click "Trigger Analysis" to manually run the agent
4. Wait a few seconds and refresh to see results

## Getting API Keys

### Anthropic Claude (Required for AI Analysis)
1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Navigate to API Keys
4. Create a new API key
5. Add to backend `.env` as `ANTHROPIC_API_KEY`

### OpenWeatherMap (Optional - for real weather data)
1. Go to https://openweathermap.org/api
2. Sign up for free account
3. Get API key from dashboard
4. Add to backend `.env` as `WEATHER_API_KEY`

### NewsAPI (Optional - for real news data)
1. Go to https://newsapi.org/
2. Sign up for free account
3. Get API key from dashboard
4. Add to backend `.env` as `NEWS_API_KEY`

**Note**: The system works with mock data if API keys are not provided, so you can test without them!

## Troubleshooting

### Backend won't start
- Check PostgreSQL is running: `pg_isready`
- Verify database exists: `psql -l | grep supply_chain`
- Check `.env` file has correct database credentials
- Check port 3001 is not in use

### Frontend can't connect to backend
- Verify backend is running on port 3001
- Check `NEXT_PUBLIC_API_URL` in frontend `.env`
- Check browser console for CORS errors
- Verify backend CORS settings allow frontend URL

### No data showing
- Click "Trigger Analysis" button to manually run agent
- Wait for agent to complete (check agent status)
- Refresh the page
- Check backend logs for errors

### Database errors
- Ensure PostgreSQL is running
- Check database credentials in `.env`
- Try recreating database: `dropdb supply_chain && createdb supply_chain`

## Next Steps

1. **Configure API Keys**: Add your Anthropic API key for AI analysis
2. **Customize Data Sources**: Modify data source parameters in `backend/src/agent/agent.service.ts`
3. **Add More Data Sources**: Follow the guide in main README.md
4. **Customize UI**: Modify components in `frontend/components/`
5. **Deploy**: Follow deployment guides for your hosting platform

## Development Tips

- Backend auto-reloads on file changes
- Frontend hot-reloads automatically
- Database schema auto-syncs in development
- Agent runs every 5 minutes automatically (or trigger manually)
- Frontend auto-refreshes data every 30 seconds
