#!/bin/bash

# Create the small early-stage label set documented in docs/LABELS.md.
# Requires GitHub CLI (gh) to be installed and authenticated.

echo "Setting up MLOX GitHub labels..."

if ! command -v gh &> /dev/null; then
    echo "GitHub CLI (gh) is not installed. Install it first:"
    echo "https://cli.github.com/"
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo "Authenticate with GitHub CLI first:"
    echo "gh auth login"
    exit 1
fi

create_label() {
    local name="$1"
    local color="$2"
    local description="$3"

    echo "Creating or updating label: $name"
    gh label create "$name" --color "$color" --description "$description" 2>/dev/null || \
    gh label edit "$name" --color "$color" --description "$description" 2>/dev/null || \
    echo "Could not create/update label: $name"
}

echo "Creating type labels..."
create_label "type:bug" "d73a4a" "Broken behavior"
create_label "type:feature" "0075ca" "New capability or larger user-visible change"
create_label "type:documentation" "0052cc" "Documentation, examples, or website content"
create_label "type:maintenance" "fef2c0" "Refactoring, dependencies, tests, CI, or cleanup"
create_label "type:question" "d876e3" "Open usage, design, or product question"

echo "Creating exceptional state labels..."
create_label "priority:urgent" "b60205" "Needs immediate maintainer attention"
create_label "status:blocked" "b60205" "Waiting on an external dependency or decision"
create_label "status:needs-info" "d876e3" "Waiting on reporter details before work can start"

echo "Creating special labels..."
create_label "good first issue" "7057ff" "Small, well-scoped task for a new contributor"
create_label "help wanted" "008672" "External contribution is welcome"

echo ""
echo "Label setup complete."
echo ""
echo "Next steps:"
echo "1. Review labels in repository settings."
echo "2. Remove labels that are not listed in docs/LABELS.md if unused."
echo "3. Keep docs/LABELS.md as the source of truth."
