<script module>
  // I'm currently working from this guide:
  //  https://storybook.js.org/tutorials/intro-to-storybook/svelte/en/screen/
  import { defineMeta } from "@storybook/addon-svelte-csf";

  import TableWrapper from "../../.storybook/components/TableWrapper.svelte";

  import PurePart from "$lib/components/PurePart.svelte";

  // More on how to set up stories at: https://storybook.js.org/docs/writing-stories
  const { Story } = defineMeta({
    title: "Library/PurePart",
    component: PurePart,
    tags: ["autodocs"],
    argTypes: {},
    args: {},
    decorators: [
      () => ({
        Component: TableWrapper
      })
    ]
  });

  // 👇 The mocked data that will be used in the story
  export const TestData = {
    id: 3,
    name: "test part",
    description: "the best test part",
    value: "3.3u",
    tolerance: null,
    loading_limit: null,
    unit: 2,
    symbol: "T",
    package_id: 69,
    equivalent_to_id: null,
    vendor_parts: []
  };
</script>

<!-- More on writing stories with args: https://storybook.js.org/docs/writing-stories/args -->
<Story name="Default" args={{ data: TestData, loading: false, error: null }} />

<Story name="Error" args={{ data: TestData, loading: false, error: { message: "error state" } }} />
<Story name="Loading" args={{ data: TestData, loading: true, error: null }} />
