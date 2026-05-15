import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{js,ts,jsx,tsx,mdx}', './components/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        securedrop: {
          primary: '#3D92CB',
          secondary: '#0C4763',
          accent: '#6DBB48',
          surface: '#AECFD5',
          background: '#FDFDFD',
        },
      },
    },
  },
  plugins: [],
};

export default config;
