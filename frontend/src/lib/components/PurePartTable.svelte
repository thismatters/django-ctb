<script lang="ts">
  import DataTable, { Body, Head, Row, Cell } from "@smui/data-table";
  import PurePart from "$lib/components/PurePart.svelte";
  import type { ResourceState } from "$lib/api/useResource.svelte";

  import type { Part } from "$lib/api/generated";

  const { data, loading, error }: ResourceState<Array<Part>> = $props();
</script>

<DataTable table$aria-label="Parts List" style="width: 100%;">
  <Head>
    <Row>
      <Cell>Symbol</Cell>
      <Cell>Name</Cell>
      <Cell>Value</Cell>
      <Cell>Unit</Cell>
    </Row>
  </Head>
  <Body>
    {#if error}
      <PurePart {error} />
    {:else if loading}
      <PurePart {loading} />
    {:else}
      {#each data as part (part.id)}
        <PurePart data={part} />
      {/each}
    {/if}
  </Body>
</DataTable>

<style>
  .parts-table {
    width: 100%;
  }
</style>
