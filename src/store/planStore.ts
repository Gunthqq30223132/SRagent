import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type {
  PlanInput,
  PlanPatientData,
  SelectedSurgery,
  SelectedComorbidity,
  GeneratedPlan,
  SavedPlan,
  AnaesthesiaType,
} from '@/types/medical'

type WizardStep = 1 | 2 | 3

interface PlanWizardState {
  step: WizardStep
  patient: PlanPatientData
  surgery: SelectedSurgery | null
  comorbidities: SelectedComorbidity[]
  isEmergency: boolean
  preferredAnaesthesia: AnaesthesiaType | undefined
  generatedPlan: GeneratedPlan | null
}

interface PlanStore extends PlanWizardState {
  // Wizard navigation
  setStep: (step: WizardStep) => void
  nextStep: () => void
  prevStep: () => void

  // Patient data
  setPatient: (patient: Partial<PlanPatientData>) => void

  // Surgery selection
  setSurgery: (surgery: SelectedSurgery | null) => void
  setIsEmergency: (val: boolean) => void
  setPreferredAnaesthesia: (type: AnaesthesiaType | undefined) => void

  // Comorbidities
  toggleComorbidity: (c: SelectedComorbidity) => void
  clearComorbidities: () => void

  // Generated plan
  setGeneratedPlan: (plan: GeneratedPlan) => void

  // Build input object
  buildPlanInput: () => PlanInput | null

  // Reset wizard
  resetWizard: () => void
}

interface SavedPlansStore {
  savedPlans: SavedPlan[]
  savePlan: (plan: SavedPlan) => void
  deletePlan: (id: string) => void
  clearAll: () => void
}

const defaultPatient: PlanPatientData = {
  weightKg: 60,
  ageYears: 40,
  ageValue: 40,
  ageUnit: 'years',
  heightCm: 165,
  sex: 'male',
  allergies: [],
  currentMedications: [],
}

const defaultWizard: PlanWizardState = {
  step: 1,
  patient: defaultPatient,
  surgery: null,
  comorbidities: [],
  isEmergency: false,
  preferredAnaesthesia: undefined,
  generatedPlan: null,
}

export const usePlanStore = create<PlanStore>((set, get) => ({
  ...defaultWizard,

  setStep: (step) => set({ step }),
  nextStep: () => set((s) => ({ step: Math.min(s.step + 1, 3) as WizardStep })),
  prevStep: () => set((s) => ({ step: Math.max(s.step - 1, 1) as WizardStep })),

  setPatient: (partial) =>
    set((s) => ({ patient: { ...s.patient, ...partial } })),

  setSurgery: (surgery) => set({ surgery }),
  setIsEmergency: (val) => set({ isEmergency: val }),
  setPreferredAnaesthesia: (type) => set({ preferredAnaesthesia: type }),

  toggleComorbidity: (c) =>
    set((s) => {
      const exists = s.comorbidities.some(
        (x) => x.conditionId === c.conditionId,
      )
      return {
        comorbidities: exists
          ? s.comorbidities.filter((x) => x.conditionId !== c.conditionId)
          : [...s.comorbidities, c],
      }
    }),

  clearComorbidities: () => set({ comorbidities: [] }),

  setGeneratedPlan: (plan) => set({ generatedPlan: plan }),

  buildPlanInput: () => {
    const { patient, surgery, comorbidities, isEmergency, preferredAnaesthesia } = get()
    if (!surgery) return null
    return { patient, surgery, comorbidities, isEmergency, preferredAnaesthesia }
  },

  resetWizard: () => set(defaultWizard),
}))

export const useSavedPlansStore = create<SavedPlansStore>()(
  persist(
    (set) => ({
      savedPlans: [],

      savePlan: (plan) =>
        set((s) => ({
          savedPlans: [plan, ...s.savedPlans].slice(0, 50), // giới hạn 50 kế hoạch
        })),

      deletePlan: (id) =>
        set((s) => ({
          savedPlans: s.savedPlans.filter((p) => p.id !== id),
        })),

      clearAll: () => set({ savedPlans: [] }),
    }),
    { name: 'anaesthesia-vn-saved-plans' },
  ),
)
