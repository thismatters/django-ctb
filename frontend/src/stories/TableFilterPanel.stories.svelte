<script module>
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import TableFilterPanel from "$lib/components/TableFilterPanel.svelte";

  import * as TableFilterOptionsListStories from "./TableFilterOptionsList.stories.svelte";

  const { Story } = defineMeta({
    title: "Library/TableFilterPanel",
    component: TableFilterPanel,
    tags: ["autodocs"],
    argTypes: {},
    args: {
      filterParams: {}
    },
    decorators: [],
    render: templateSnippet
  });

  export const TestData = [
    {
      options: ["one", "two", "thr3e"],
      field_name: "test_one",
      supports_exact: true,
      supports_isnull: false,
      choice_options: null
    },
    {
      options: ["one", "two", "thr3e"],
      field_name: "test_two",
      supports_exact: true,
      supports_isnull: true,
      choice_options: null
    },
    {
      options: ["one", "two", "thr3e", "four", "five", "six", "seven", "eight", "nine", "ten"],
      field_name: "test_three",
      supports_exact: true,
      supports_isnull: false,
      choice_options: null
    }
  ];
</script>

{#snippet templateSnippet(args)}
  <TableFilterPanel {...args} bind:filterParams={args.filterParams} />
  <p>
    Selected Options: test_one: {args.filterParams.test_one}, test_two: {args.filterParams
      .test_two}, test_three: {args.filterParams.test_three}
  </p>
{/snippet}

<Story
  name="Default"
  args={{
    data: { filters: TestData },
    filterParams: { test_one: ["thr3e"], test_two: ["two"], test_three: ["one"] }
  }}
/>

<Story name="Loading" args={{ loading: true }} />

<Story name="Error" args={{ error: { message: "bad error" } }} />
