# AnesthOs Project Guidelines

## Tech Stack
- **Framework**: Next.js (App Router)
- **Styling**: TailwindCSS
- **Database**: SQLite (native addon)
- **UI Components**: Radix UI
- **Icons**: Lucide React

## Medical Safety Rule
- **No PII/PHI Outbound**: Absolutely no Personally Identifiable Information (PII) or patient-identifying data may be sent to any API or external service.

## Standard Development Commands
- **Development**: `npm run dev`
- **Testing**: `npm run test`
- **Linting**: `npm run lint`
- **Building**: `npm run build`

## Strict Code Rules
- **TypeScript**: Pure TypeScript with strict mode enabled. The `any` type is strictly forbidden.
- **Clinical Math**: All clinical math and drug dosing calculations must use only native `Math` functions. Do not install or import external mathematical npm packages.
- **LaTeX Documentation**: All dosage formulas in code comments must be documented using LaTeX format. E.g., `// $Dose = C \times Weight$`.
- **Approved Dependencies**: Only the following approved dependencies may be used:
  - Next.js (App Router)
  - TailwindCSS
  - Radix UI
  - Lucide React
  - SQLite (native addon)
- **No Plagiarism**: Do not copy-paste business or clinical logic from open-source repositories.
- **Security**: No arbitrary shell script execution or remote script fetching in code or pipelines.
- **Rule Source of Truth**: All medical rules, constraints, and dosing limits must derive strictly from specifications in `.anesthos/specs/` files.
