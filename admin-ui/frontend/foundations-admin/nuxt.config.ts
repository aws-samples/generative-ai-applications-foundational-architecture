// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  devtools: { enabled: false },
  ssr: false,
  router: {
    options: {
      hashMode: true
    }
  },
  plugins: ['~/plugins/cognito-config.js'],
  vite: {
   define: {
    global: {}
  }
  },
  css: ['~/assets/css/main.css'],
  app: {
    head:{
      script: [
        {
          src: '/swagger-ui-bundle.js'
        },
        {
          src: '/swagger-ui-standalone-preset.js'
        }
      ]
    }
  },
  postcss: {
    plugins: {
      tailwindcss: {},
      autoprefixer: {},
    },
  },
  modules: ["nuxt-auth-utils", "@nuxt/ui", "nuxt-security"],
  runtimeConfig: {
    public:{
      baseUrl: '<your-api-gateway-url>'
    }
  },
  security: {
    headers: {
      contentSecurityPolicy: {
        'default-src': ["'self'"],
        'script-src': ["'self'"],
        'style-src': ["'self'", "'unsafe-inline'"],
        'connect-src': ["'self'", "<your-api-gateway-url>", "https://<cognito_domain>/oauth2/token","https://api.iconify.design","https://api.unisvg.com", "https://api.simplesvg.com"]
      }
    }
  }
})