export default defineNuxtRouteMiddleware((to, from) => {

    const runtimeConfig = useRuntimeConfig();
    const BASE_URL = runtimeConfig.public.baseUrl
    const response = fetch(BASE_URL + 'admin/auth/status', {
    method: 'GET',    
    credentials: 'include'}).then(response => {

        if (!response.ok) {
            window.location.href = '/';
        }
        else{
            console.log('response is ok');
        }
    }
    ).catch(error => {
        window.location.href = '/';
    });
    return response;

  });