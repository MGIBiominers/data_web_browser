import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Static build, no server runtime. See ../DESIGN.md for why: the metadata
// this app displays lives in S3 and is fetched at runtime (src/api.js), so
// the built bundle itself never needs to be rebuilt when the underlying
// data changes -- only the JSON in S3 does.
export default defineConfig({
  plugins: [react()],
  base: './',
})
