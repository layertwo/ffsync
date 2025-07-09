import {FlatCompat} from "@eslint/eslintrc";
import js from "@eslint/js";
import stylisticJs from "@stylistic/eslint-plugin-js";
import tsParser from "@typescript-eslint/parser";
import prettier from "eslint-plugin-prettier";
import path from "node:path";
import {fileURLToPath} from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const compat = new FlatCompat({
    baseDirectory: __dirname,
    recommendedConfig: js.configs.recommended,
    allConfig: js.configs.all,
});

export default [
    {
        ignores: ["**/*.d.ts", "**/*.js", "!**/.eslintrc.js", "!**/.prettierrc.js"],
    },
    ...compat.extends("prettier", "plugin:@typescript-eslint/recommended"),
    {
        plugins: {
            prettier,
            "@stylistic/js": stylisticJs,
        },
        languageOptions: {
            parser: tsParser,
            ecmaVersion: 2020,
            sourceType: "module",
        },
        rules: {
            "prettier/prettier": ["error"],
            "@stylistic/js/semi": ["error", "always"],
            "@stylistic/js/comma-dangle": ["error", "always-multiline"],
            "@stylistic/js/indent": ["error", 4],
            "@typescript-eslint/no-explicit-any": "off",
            "@typescript-eslint/ban-ts-comment": [
                "error",
                {
                    "ts-ignore": "allow-with-description",
                },
            ],
            "@typescript-eslint/no-unused-vars": [
                "error",
                {
                    argsIgnorePattern: "^_",
                },
            ],
            "eol-last": ["error", "always"],
            "max-len": [
                "error",
                {
                    code: 100,
                    ignoreUrls: true,
                },
            ],
        },
    },
    {
        files: ["**/package.json"],
        rules: {
            "@stylistic/js/semi": "off",
            "@stylistic/js/comma-dangle": "off",
            "max-len": "off",
            "@typescript-eslint/no-unused-expressions": "off",
        },
    },
];
