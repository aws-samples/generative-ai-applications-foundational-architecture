<template>
  <div class="w-full bg-gray-100 p-0 h-screen flex flex-col justify-center items-center">
    <div class="w-full flex h-12 px-4 flex bg-gray-800 text-white font-bold justify-between items-center">
      <div class="flex px-0 w-full justify-between items-center mx-auto" style="width: 1200px">
        <div class="flex justify-start items-center">
          <!-- <img src="~/assets/aws.svg" style="width: 30px; margin-top: 2px" class="mr-3" /> -->
          <UIcon name="mdi:code-block-tags" class="mr-1 text-xl -mt-1" dynamic style="color:#f99f33"/>
          <div class="font-semibold text-white mr-2 flex justify-start items-center"
            style="margin-top: -2px; font-size: 16px !important">
            Generative AI Foundations
            <div class="px-2 rounded-sm text-gray-200 text-sm ml-3 border-l border-gray-600">Admin Portal</div>
          </div>
        </div>
        <div class="text-white flex justify-center items-center">

          <button @click="logout"
            class="p-0 rounded bg-none text-white text-lg font-thin flex justify-start items-center">
            <Icon name="material-symbols:logout" class="mr-1" />
            
          </button>
        </div>
      </div>

    </div>

    <div class="bg-white w-full flex justify-center border-b">

      <div class="space=x-4 px-0 bg-inherit flex justify-start items-center" style="width: 1200px;">

        <a href="/#/app/applications"
          class="h-12 border-b-2 pr-4 border-r font-semibold text-sm text-gray-700 flex justify-center items-center" :class="{
            'border-tab-aws-active': route.fullPath.includes('applications'),
            'border-tab-aws': !route.fullPath.includes('applications'),
          }">
          <UIcon name="material-symbols:settings-applications-outline" class="text-gray-500 mr-1 text-lg" dynamic />
          Applications & Services
        </a>

        <a href="/#/app/metrics" class="h-12 border-b-2 px-0 px-4 border-r font-semibold text-sm text-gray-700 flex justify-center items-center"
          :class="{
            'border-tab-aws-active': route.fullPath.includes('metrics'),
            'border-tab-aws': !route.fullPath.includes('metrics'),
          }">
          <UIcon name="material-symbols:query-stats" class="text-gray-500 mr-1 text-lg"
            style=" margin-top: -1px" dynamic />
          Metrics
        </a>

        <a href="/#/app/playground"
          class="h-12 border-b-2 px-4 font-semibold text-sm text-gray-700 flex justify-center items-center" :class="{
            'border-tab-aws-active': route.fullPath.includes('playground'),
            'border-tab-aws': !route.fullPath.includes('playground'),
          }">
          <UIcon name="material-symbols:display-settings-outline-sharp" class="text-gray-500 mr-1 text-;g"
            style=" margin-top: -1px" dynamic />
          API Playground
        </a>

      </div>

    </div>




    <div class="flex flex-col flex-1 flex-grow rounded-lg overflow-hidden w-full bg-gray-100">

      <div class="mx-auto flex flex-col flex-1 flex-grow p-0" style="width: 1200px">
        <NuxtPage />
      </div>
      <UNotifications />
    </div>
  </div>
</template>

<script setup>

import cognitoConfig from '~/plugins/cognito-config';

const route = useRoute();
const runtimeConfig = useRuntimeConfig();
const BASE_URL = runtimeConfig.public.baseUrl;



const logout = () => {

  const { domain, clientId, redirectUri } = cognitoConfig;
  const logoutUrl = `https://${domain}/logout?client_id=${clientId}&logout_uri=${redirectUri}&response_type=code&scope=email+openid`;

  fetch(BASE_URL + 'admin/unset_cookie', {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
  }).then((response) => {
      window.location = logoutUrl;
  }).catch((error) => {
    console.error('Error logging out', error);
  });

};

onMounted(() => {
  console.log('Shell Page Mounted');
});

</script>
<style scoped>
.border-tab-aws-active {
  border-bottom: 3px solid #0972D3;
  font-weight: 600;
  color:#0972D3;
}

.border-tab-aws {
  border-bottom: 3px solid #ffffff;
}

/* Hide vertical scrollbar by default */
* {
  overflow-y: auto;
  scrollbar-width: none;
  /* For Firefox */
}

*::-webkit-scrollbar {
  width: 0;
  /* For WebKit browsers */
}
</style>
