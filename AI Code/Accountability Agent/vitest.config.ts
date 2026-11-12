import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['server/**/*.test.ts'],
    exclude: ['build-server/**', 'dist/**', 'node_modules/**'],
  },
});
