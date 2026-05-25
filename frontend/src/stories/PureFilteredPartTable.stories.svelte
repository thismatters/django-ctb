<script module>
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import PureFilteredPartTable from "$lib/components/PureFilteredPartTable.svelte";

  import * as TableFilterPanelStories from "./TableFilterPanel.stories.svelte";
  import * as PurePartTableStories from "./PurePartTable.stories.svelte";

  const { Story } = defineMeta({
    title: "Library/PureFilteredPartTable",
    component: PureFilteredPartTable,
    tags: ["autodocs"],
    argTypes: {},
    args: {},
    decorators: [],
    render: templateSnippet
  });

  const TestData = {
    filterMetaResourceState: {
      data: { filters: TableFilterPanelStories.TestData },
      error: null,
      loading: false
    },
    partListResourceState: {
      data: PurePartTableStories.TestData,
      error: null,
      loading: false
    }
  };
</script>

{#snippet templateSnippet(args)}
  <PureFilteredPartTable {...args} bind:queryParams={args.queryParams} />
  <p>Query Params: {JSON.stringify(args.queryParams)}</p>
{/snippet}

<Story name="Default" args={{ ...TestData, queryParams: {} }} />
