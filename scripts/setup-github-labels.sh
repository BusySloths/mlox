#!/bin/bash

# MLOX GitHub Labels Setup Script
# This script creates the standardized label set for the MLOX repository
# Requires GitHub CLI (gh) to be installed and authenticated

echo "🏷️  Setting up MLOX GitHub labels..."

# Check if gh CLI is available
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed. Please install it first:"
    echo "   https://cli.github.com/"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "❌ Please authenticate with GitHub CLI first:"
    echo "   gh auth login"
    exit 1
fi

echo "✅ GitHub CLI is ready"

# Function to create or update a label
create_label() {
    local name="$1"
    local color="$2"
    local description="$3"
    
    echo "Creating label: $name"
    gh label create "$name" --color "$color" --description "$description" 2>/dev/null || \
    gh label edit "$name" --color "$color" --description "$description" 2>/dev/null || \
    echo "⚠️  Could not create/update label: $name"
}

echo "📝 Creating type labels..."
create_label "type:bug" "d73a4a" "Something isn't working correctly"
create_label "type:feature" "0075ca" "New functionality or capabilities"
create_label "type:enhancement" "a2eeef" "Improvements to existing features"
create_label "type:documentation" "0052cc" "Documentation changes or additions"
create_label "type:maintenance" "fef2c0" "Code cleanup, refactoring, dependency updates"
create_label "type:question" "d876e3" "Questions about usage or implementation"

echo "🚨 Creating priority labels..."
create_label "priority:critical" "b60205" "Critical bugs, security issues, or blocking problems"
create_label "priority:high" "d93f0b" "Important features or significant bugs"
create_label "priority:medium" "fbca04" "Standard priority items"
create_label "priority:low" "0e8a16" "Nice-to-have improvements, minor issues"

echo "🔧 Creating component labels..."
create_label "component:cli" "5319e7" "Command line interface related"
create_label "component:ui" "1d76db" "Web user interface related"
create_label "component:infrastructure" "b4a7d6" "Core infrastructure management"
create_label "component:services" "c2e0c6" "Service integrations and management"
create_label "component:security" "d4c5f9" "Security, authentication, secrets management"
create_label "component:docs" "e99695" "Documentation and guides"
create_label "component:testing" "f9d0c4" "Testing infrastructure and test cases"
create_label "component:ci-cd" "c5def5" "Continuous integration and deployment"

echo "📊 Creating status labels..."
create_label "status:needs-triage" "fbca04" "Needs initial review and categorization"
create_label "status:blocked" "b60205" "Blocked by external dependencies or decisions"
create_label "status:in-progress" "0052cc" "Currently being worked on"
create_label "status:ready-for-review" "0e8a16" "Ready for code review"
create_label "status:waiting-for-feedback" "d876e3" "Waiting for feedback from reporter or maintainer"

echo "⏱️  Creating effort labels..."
create_label "effort:small" "c2e0c6" "1-2 days of work"
create_label "effort:medium" "bfdadc" "3-5 days of work"
create_label "effort:large" "f9d0c4" "1-2 weeks of work"
create_label "effort:xl" "e99695" "More than 2 weeks of work"

echo "⭐ Creating special labels..."
create_label "good-first-issue" "7057ff" "Suitable for new contributors"
create_label "help-wanted" "008672" "Community contributions welcome"
create_label "breaking-change" "b60205" "Introduces breaking changes"
create_label "duplicate" "cfd3d7" "Duplicate of another issue"
create_label "invalid" "e4e669" "Invalid issue or doesn't meet criteria"
create_label "wontfix" "ffffff" "Issue will not be fixed or implemented"
create_label "dependencies" "0366d6" "Updates to dependencies"
create_label "security" "d73a4a" "Security-related issues"

echo ""
echo "✅ Label setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Review the labels in your repository settings"
echo "   2. Start applying labels to existing issues"
echo "   3. Update your issue templates to use these labels"
echo "   4. Share the labeling guidelines with your team"
echo ""
echo "📚 Documentation:"
echo "   - Labels Guide: docs/LABELS.md"
echo "   - Project Planning: docs/PROJECT_PLANNING.md"
echo "   - GitHub Project Guide: docs/GITHUB_PROJECT.md"