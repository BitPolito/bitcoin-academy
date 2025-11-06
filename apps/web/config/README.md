# Frontend Configuration

Configuration files for the Next.js application.

## Files

- **jest.config.js** - Jest testing framework configuration (kept in root for Jest to find it)
- **jest.setup.js** - Jest environment setup (kept in root for Jest to find it)

## Build Configuration

These configuration files must be in the root directory for Next.js and tools to locate them:

- `next.config.js` - Next.js configuration
- `tsconfig.json` - TypeScript configuration
- `tailwind.config.js` - Tailwind CSS configuration
- `postcss.config.js` - PostCSS configuration

## Note

Jest and other build tools require these files in the root directory. They cannot be moved to a config/ subdirectory.
