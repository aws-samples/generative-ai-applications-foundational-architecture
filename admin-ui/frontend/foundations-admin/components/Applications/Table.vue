<template>
    <div class="mx-4  pb-3 border-b flex justify-between items-center ">
        <div class="font-bold text-xl text-gray-800">Applications</div>


        <div>
            <UButton label="Register New
            App" class="bg-white rounded-full text-blue-700 rounded-full border-blue-500 border-2 text-xs px-3 py-2 hover:bg-orange-500 hover:text-white hover:border-white" @click="isOpen = true" />

            <UModal v-model="isOpen">
                <div class="p-4">
                    <h1 class="text- font-semibold mb-4">Register New App</h1>
                    <div class="h-1 border-b mb-6">

                    </div>
                    <div class="mb-4">
                        <label for="app_name" class="block text-sm ">App Name</label>
                        <input v-model="app_name" type="text" id="app_name" class="border w-full p-2 rounded-sm" />
                    </div>
                    <div class="mb-4">
                        <label for="description" class="block text-sm ">Description</label>
                        <textarea v-model="description" id="description"
                            class="border w-full p-2 rounded-sm"></textarea>
                    </div>

                    <button @click="create_app_client"
                        class="bg-orange-500 text-white text-sm px-3 py-2 rounded-sm">Submit</button>
                    <button @click="close_modal"
                        class="bg-gray-500 text-white text-sm px-3 py-2 ml-4 rounded-sm">Cancel</button>
                </div>
            </UModal>
        </div>
    </div>
    <UTable :rows="apps" :columns="columns" class="border m-4 text-gray-800 shadow-sm text-base">


        <template #app_name-data="{ row }">
            <div class="text-gray-700 text-base ">{{ row.app_name }}</div>
        </template>

        <template #app_id-data="{ row }">
            <div class="text-gray-700 text-base ">
                {{ row.app_id }}
            </div>
        </template>

        <template #description-data="{ row }">
            <UTooltip>
                <template #text>
                    <span class="italic">{{row.description}}</span>
                </template>
                <!-- <div class="text-xs">{{ row.description }}</div>
            <div class="text-xs" v-if="row.description !== null && row.description !== ''">
                {{ truncate(row.description, 3)  }}</div>
            <div class="text-xs" v-else>
                No description
            </div> -->
        </UTooltip>
        </template>

        <template #date_created-data="{ row }">
            <div class="text-xs">{{ row.date_created }}</div>

        </template>

        <template #status-data="{ row }">
            <span v-if="row.status === 'active'" class="text-green-500 font-semibold">
                {{ row.status }}
            </span>
            <span v-else class="text-red-500 font-semibold">
                {{ row.status }}
            </span>
        </template>

        <template #credentials-data="{ row }">
            <div class="flex justify-center items-center">
                <UPopover class="p-0" >
                    <UIcon name="solar:key-minimalistic-outline" class="text-blue-500 text-lg mt-2 mr-3" dynamic />

                    <template #panel>
                        <div class="p-8 text-xs text-black">
                            <div class="mb-2 border-b px-0 py-2 text-base">
                                Connection Details
                            </div>
                            <table class="p-3 border">
                                <tr class="py-2 border-b">
                                    <td class="font-semibold p-2">Secret Arn:</td>
                                    <td>{{row.secret_arn}}</td>
                                </tr>
                                <tr class="py-2 border-b bg-gray-50">
                                    <td class="font-semibold p-2">Client ID:</td>
                                    <td>{{row.client_id}}</td>
                                </tr>
                                <tr class="py-2 border-b">
                                    <td class="font-semibold p-2">User Pool ID:</td>
                                    <td>{{row.app_user_pool_id}}</td>
                                </tr>
                                <tr class="py-2 border-b bg-gray-50">
                                    <td class="font-semibold p-2">User Pool Domain:</td>
                                    <td>{{row.platform_domain}}</td>
                                </tr>
                            </table>
                            
                            <div class="mt-4 px-2 italic">
                                Share the secret arn with the external client. Provide read-only access to the secret arn to the client. <br />
                                Please check sample code for more details.
                            </div>
                        </div>
                    </template>
                </UPopover>

                <UPopover class="p-0">
                    <UTooltip text="Unregister App" v-if="row.status === 'active'">
                    <button @click="deactivate_app_client(row.app_id)" >
                    
                        
                    <UIcon name="solar:link-broken-bold" class="text-red-500 text-lg" dynamic />

                    </button>
                </UTooltip>

                <UTooltip text="Register App" v-else>
                    <button @click="activate_app_client(row.app_id)"  >
                        <UIcon name="solar:link-bold" class="text-green-500 text-lg" dynamic />
                    </button>

                </UTooltip>

                    <!-- <template #panel>
                        <div class="p-4">
                            {{row.secret_arn}}
                        </div>
                    </template> -->
                </UPopover>

                <!-- <a :href="`/app/account/${row.app_id}/credentials`" class="ml-6">
                  

                </a> -->
            </div>
        </template>
    </UTable>
</template>

<script setup lang="ts">

const runtimeConfig = useRuntimeConfig();
const BASE_URL = runtimeConfig.public.baseUrl

const isOpen = ref(false);
const app_name = ref('');
const description = ref('');
const toast = useToast();

const columns = [{
    key: 'app_name',
    label: 'App Name'
}, {
    key: 'app_id',
    label: 'App ID'
}, {
    key: 'description',
    label: 'Description'
},
{
    key: 'date_created',
    label: 'Date Created'
},
{
    key: 'status',
    label: 'Status'
}
    ,
{
    key: 'credentials',
    label: 'Actions',
}
]

const apps = ref([])

function close_modal() {
    isOpen.value = false;
    app_name.value = '';
    description.value = '';
}

function truncate(value, length) {
        if (value.length > length) {
            return value.substring(0, length) + "...";
        } else {
            return value;
          }
      }

async function deactivate_app_client(app_id: string) {
    const response = await fetch(BASE_URL + 'admin/platform/deactivate_app_client', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
            app_id: app_id
        })
    });

    const data = await response.json();
    if (response.status !== 200) {
        toast.add({
            id: 'app_deactivated',
            title: 'Application Deactivation Failed',
            description: 'Application could not be unregistered',
            icon: 'clarity:error-standard-solid',
            timeout: 5000,
            color: 'red'
        })
        return;
    }
    toast.add({
        id: 'app_deactivated',
        title: 'Application Deactivated',
        description: 'Application has been unregistered successfully',
        icon: 'clarity:success-standard-solid',
        timeout: 5000,
        color: 'yellow'
    })
    get_all_app_clients();
}

async function activate_app_client(app_id: string) {
    const response = await fetch(BASE_URL + 'admin/platform/activate_app_client', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
            app_id: app_id
        })
    });
    const data = await response.json();
    if (response.status !== 200) {
        toast.add({
            id: 'app_activated',
            title: 'Application Activation Failed',
            description: 'Application could not be registered',
            icon: 'clarity:error-standard-solid',
            timeout: 5000,
            color: 'red'
        })
        return;
    }
    toast.add({
        id: 'app_activated',
        title: 'Application Activated',
        description: 'Application has been registered successfully',
        icon: 'clarity:success-standard-solid',
        timeout: 5000
    })
    get_all_app_clients();
}

async function create_app_client() {

    // strip and check if the fields are empty

    if (app_name.value.trim() === '' || description.value.trim() === '') {
        toast.add({
            id: 'empty_fields',
            title: 'Empty Fields',
            description: 'Please fill in all fields',
            icon: 'clarity:error-standard-solid',
            timeout: 5000,
            color: 'red'
        })
        return;
    }

    const response = await fetch(BASE_URL + 'admin/platform/create_app_client', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
            app_name: app_name.value,
            description: description.value
        })
    });

    const data = await response.json();
    if (response.status !== 200) {
        toast.add({
            id: 'app_created',
            title: 'Application Registration Failed',
            description: 'Application could not be registered',
            icon: 'clarity:error-standard-solid',
            timeout: 5000,
            color: 'red'
        })
        return;
    }

    close_modal();
    get_all_app_clients();
    toast.add({
        id: 'app_registered',
        title: 'Application Registered',
        description: 'Application has been registered successfully',
        icon: 'clarity:success-standard-solid',
        timeout: 5000
    })
}

async function get_all_app_clients() {
    await nextTick();
    useFetch(BASE_URL + 'admin/platform/get_all_app_clients', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include'
    }).then((res) => {
        apps.value = res.data.value;
    });


}

onMounted(() => {
    get_all_app_clients();
});

</script>