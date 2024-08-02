<!-- pages/index.vue -->
<!-- <template>
  <div>
    <h1>Welcome to the Nuxt App</h1>
    <button @click="login">Login with Cognito</button>
  </div>
</template> -->

<template>
  <div class="flex flex-col w-full h-screen justify-center items-center">
    <div class="my-4 text-4xl font-bold">GenAI Foundations Admin Portal</div>
    <button @click="login" class="px-3 py-3 rounded bg-green-700 text-white">Login with Cognito</button>
  </div>
</template>

<script>
import cognitoConfig from '~/plugins/cognito-config';
export default {
  methods: {
    login() {
      const { domain, clientId, redirectUri } = cognitoConfig;
      const loginUrl = `https://${domain}/login?response_type=code&scope=email&client_id=${clientId}&redirect_uri=${redirectUri}`;
      window.location.href = loginUrl;
    }
  }
};
</script>