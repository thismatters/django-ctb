<script lang="ts">
  import type { FilterFields, FilterMeta } from "$lib/api/generated";
  import type { ResourceState } from "$lib/api/useResource.svelte";
  interface Props {
    filterParams?: Record<string, Array<string>>;
    onsearch: () => null;
  }
  let {
    data,
    error,
    loading,
    onsearch,
    filterParams = $bindable({})
  }: ResourceState<FilterMeta> | Props = $props();

  const setSelectedOptions = (idx: number, options: Array<string>) => {
    const field_name = data.filters[idx].field_name;
    filterParams[field_name] = options;
  };

  function resetFilters() {
    filterParams = {};
  }
</script>

<div class="panel-container">
  <div class="flex-row">
    {#if error}
      <div class="flex-item">{error.message}</div>
    {:else if loading}
      <div class="flex-item">...loading</div>
    {:else}
      {#each data.filters as filter, index}
        <div class="flex-item">
          <TableFilterOptionsList
            {...filter}
            bind:selectedOptions={
              () => filterParams[filter.field_name] || [], (v) => setSelectedOptions(index, v)
            }
          />
        </div>
      {/each}
    {/if}
  </div>
  <div class="panel-controls">
    <button onclick={onsearch}>Search</button>
    <button onclick={resetFilters}>Reset</button>
  </div>
</div>

<style>
  .flex-row {
    display: flex;
    flex-direction: row;
    min-width: 500px;
    max-height: 500px;
  }

  .flex-row .flex-item {
    flex-grow: 1;
  }
</style>
