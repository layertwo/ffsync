import {createRequire} from "node:module";

const require = createRequire(import.meta.url);

export default {
    plugins: [require.resolve("@trivago/prettier-plugin-sort-imports"), "prettier-plugin-pkgsort"],
    singleQuote: false,
    printWidth: 100,
    tabWidth: 4,
    bracketSpacing: false,
    importOrder: ["^aws-cdk-lib.*$", "^[./]"],
    importOrderSeparation: true,
    importOrderSortSpecifiers: true,
    importOrderParserPlugins: ["typescript", "decorators"],
    trailingComma: "all",
};
