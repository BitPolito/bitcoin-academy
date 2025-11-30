# BitPolito Academy - Next.js Frontend

This is the frontend application for BitPolito Academy built with Next.js 14.

## Project Structure

```
src/
├── app/                    # Next.js App Router pages
│   ├── api/               # API route handlers
│   ├── layout.tsx         # Root layout
│   ├── page.tsx           # Home page
│   └── globals.css        # Global styles
├── lib/
│   ├── api.ts             # HTTP client
│   ├── env.ts             # Environment variables
│   ├── auth/              # NextAuth configuration
│   ├── services/          # Business logic
│   ├── repositories/      # API wrappers
│   ├── middleware/        # Client/server middleware
│   └── rbac.ts            # Role-based access control
└── components/            # Reusable React components
```

## Setup

### Prerequisites

- Node.js 18+
- npm or yarn

### Installation

```bash
npm install
```

### Environment Variables

Create a `.env.local` file based on `.env.example`:

```bash
cp .env.example .env.local
```

Configure the following variables:

- `NEXT_PUBLIC_API_BASE_URL` - FastAPI backend URL (default: http://localhost:8000/api)
- `NEXTAUTH_SECRET` - Secret key for NextAuth sessions
- `NEXTAUTH_URL` - Application URL (default: http://localhost:3000)

## Development

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to see the application.

## Build

```bash
npm run build
npm start
```

## Type Checking

```bash
npm run type-check
```

## Linting

```bash
npm run lint
```

## Formatting

```bash
# Format code
npm run format

# Check formatting
npm run format:check
```

## Key Technologies

- **Next.js 14** - React framework with App Router
- **TypeScript** - Type-safe JavaScript
- **Tailwind CSS** - Utility-first CSS
- **NextAuth.js** - Authentication
- **React 18** - UI library

## Features

- Server-side rendering (SSR)
- Static site generation (SSG)
- API routes for server-side operations
- Authentication & Authorization
- Responsive design with Tailwind CSS
- Type-safe development with TypeScript

## Development Guidelines

### File Organization

- Pages in `src/app` use the App Router convention
- Shared components go in `src/components`
- Utility functions in `src/lib`
- API client logic in `src/lib/api.ts`
- Services for business logic in `src/lib/services`
- Repository pattern for API calls in `src/lib/repositories`

### Component Conventions

- Use TypeScript for all components
- Export components as default in the file
- Use functional components with hooks
- Prefix prop interfaces with component name (e.g., `ButtonProps`)

### API Communication

Use the typed `ApiClient` from `src/lib/api.ts`:

```typescript
import { apiClient } from '@/lib/api';

const courses = await apiClient.get<Course[]>('/courses');
await apiClient.post('/courses', courseData);
```