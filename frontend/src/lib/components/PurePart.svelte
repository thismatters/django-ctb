<script lang="ts">
  import { Row, Cell } from "@smui/data-table";

  import type { Part } from "$lib/api/generated";
  import type { ResourceState } from "$lib/api/useResource.svelte";

  const { data, loading, error }: ResourceState<Part> = $props();

  const unitEnum = ["None", "Ohm", "Farad", "Henry", "Volt", "Ampere"];
</script>

<Row>
  {#if error}
    <Cell colspan="4" class="error">{error.message}</Cell>
  {:else if loading}
    <Cell colspan="4">loading...</Cell>
  {:else}
    <Cell>{data.symbol}</Cell>
    <Cell>{data.name}</Cell>
    <Cell>{data.value}</Cell>
    <Cell>{unitEnum[data.unit]}</Cell>
  {/if}
</Row>
