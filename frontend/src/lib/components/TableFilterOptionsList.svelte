<script lang="ts">
  import type { FilterFields, FilterFieldChoice } from "$lib/api/generated";

  interface Props {
    selectedOptions: Array<string>;
  }

  let {
    field_name,
    supports_exact,
    supports_isnull,
    options,
    choice_options,
    selectedOptions = $bindable([])
  }: FilterFields | Props = $props();

  let actualOptions: Array<FilterFieldChoice> = $derived.by(() => {
    let ret: Array<FilterFieldChoice>;
    if (options !== null) {
      ret = options.map((opt) => ({ value: opt, label: opt }));
    } else {
      ret = choice_options.map((opt) => opt);
    }
    if (supports_isnull) {
      ret.unshift({ value: null, label: "(null)" });
    }
    return ret;
  });
</script>

<label
  >{field_name}
  <select multiple bind:value={selectedOptions}>
    {#each actualOptions as thisOption (thisOption.value)}
      <option value={thisOption.value}>{thisOption.label}</option>
    {/each}
  </select>
</label>

<style>
  select {
    width: 100%;
  }
</style>
