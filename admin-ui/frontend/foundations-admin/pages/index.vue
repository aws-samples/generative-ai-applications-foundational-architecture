<template>
    <div class="w-full bg-gray-100 p-0 h-screen flex flex-col justify-start items-center">
        <div class="w-full flex h-12 px-4 flex bg-gray-800 text-white font-bold justify-between items-center">
            <div class="flex px-0 w-full justify-between items-center mx-auto" style="width: 1200px">
                <div class="flex justify-start items-center">
                    <!-- <img src="~/assets/aws.svg" style="width: 30px; margin-top: 2px" class="mr-3" /> -->
                    <UIcon name="mdi:code-block-tags" class="mr-1 text-xl -mt-1" dynamic style="color:#f99f33"/>
                    <div class="font-semibold text-white mr-2 flex justify-start items-center"
                        style="margin-top: -2px; font-size: 16px !important">
                        Generative AI Foundations
                        <div class="px-2 rounded-sm text-gray-200 text-sm ml-3 border-l border-gray-600">Admin Portal
                        </div>
                    </div>
                </div>

            </div>


        </div>

        <div class="flex flex-col mx-auto mt-8 w-96 text-center justify-center items-center p-8 border bg-white" v-if="show_login">

            <div class="py-4 text- font-semibold">Welcome to Generative AI Application Foundational Platform!</div>
            <button @click="login" class="bg-white rounded-full text-blue-700 rounded-full border-blue-500 border-2 text-xs px-3 py-2 hover:bg-orange-500 hover:text-white hover:border-white">Click here to login</button>
        </div>

        <div class="flex flex-col mx-auto mt-8 w-96 text-center justify-center items-center p-8 border bg-white" v-if="!show_login">
            <UIcon name="svg-spinners:gooey-balls-1" class="text-blue-500 text-lg mt-2 mr-3" dynamic />
        </div>
    </div>

</template>

<script setup lang="ts">

import cognitoConfig from '~/plugins/cognito-config';

const runtimeConfig = useRuntimeConfig();
const BASE_URL = runtimeConfig.public.baseUrl
const is_authenticated = ref(false);
const show_login = ref(false);
const router = useRouter();

async function login() {
    const { domain, clientId, redirectUri } = cognitoConfig;
    const loginUrl = `https://${domain}/login?response_type=code&scope=email+openid&client_id=${clientId}&redirect_uri=${redirectUri}`;
    window.location.href = loginUrl;
    console.log(loginUrl);
}

async function checkAuth() {
    console.log('Checking Auth');
    const { data, pending, error, refresh, execute } = await useFetch(BASE_URL + 'admin/auth/status', {
        immediate: true,
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
        },
        onResponse: (context) => {
            is_authenticated.value = context.response.status === 200;
            if (context.response.status === 200) {
                window.location.href = '/#/app/applications';
            }
        },
        onResponseError: (context) => {
            show_login.value = true;
        },
        onRequestError: (context) => {
            show_login.value = true;
        }
    });
    await execute();
}

async function checkCode() {
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');

    if (code) {
        const { clientId, redirectUri, domain } = cognitoConfig;
        const tokenUrl = `https://${domain}/oauth2/token`;
        const params = new URLSearchParams();
        params.append('grant_type', 'authorization_code');
        params.append('client_id', clientId);
        params.append('code', code);
        params.append('redirect_uri', redirectUri);

        try {
            const response = await fetch(tokenUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                body: params.toString(),
            });

            const data = await response.json();
            const idToken = data.access_token;

            if (idToken) {

                // document.cookie = `id_token=${idToken}; path=/; SameSite=None; Secure`;
                await fetch(BASE_URL + 'admin/set_cookie', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${idToken}`
                    },
                    body: JSON.stringify({ "id_token": idToken }),
                    credentials: 'include'
                }).then(() => {
                    setTimeout(() => {
                        checkAuth();
                    }, 1000);

                }).catch((e) => alert("hello"));

            } else {
                throw new Error('No id_token found');
            }
        } catch (error) {
            console.error('Error exchanging code for token:', error);
        }
    } else {
        setTimeout(() => {
            checkAuth();
        }, 1000);
    }
}

onMounted(() => {
    setTimeout(() => {
        checkCode();
    }, 1000);
});

</script>