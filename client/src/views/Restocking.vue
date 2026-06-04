<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <!-- Budget card -->
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">{{ t('restocking.budgetCard.title') }}</h3>
      </div>
      <div class="budget-body">
        <div class="budget-value">{{ currencySymbol }}{{ budget.toLocaleString() }}</div>
        <div class="budget-sublabel">{{ t('restocking.budgetCard.sublabel') }}</div>
        <input
          type="range"
          min="0"
          max="500000"
          step="5000"
          v-model.number="budget"
          class="budget-slider"
        />
        <div class="slider-range-labels">
          <span>{{ currencySymbol }}0</span>
          <span>{{ currencySymbol }}500,000</span>
        </div>
      </div>
    </div>

    <!-- Recommendations card -->
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">{{ t('restocking.recommendations.title') }}</h3>
      </div>

      <!-- Success state replaces recommendations content -->
      <div v-if="submittedOrder" class="success-block">
        <div class="success-title">{{ t('restocking.successTitle') }}</div>
        <div class="success-message">
          {{ t('restocking.successMessage', { orderNumber: submittedOrder.order_number }) }}
        </div>
        <div class="success-actions">
          <button class="btn-primary" @click="goToOrders">
            {{ t('restocking.viewOrders') }}
          </button>
          <button class="btn-secondary" @click="resetState">
            {{ t('restocking.submitAnother') }}
          </button>
        </div>
      </div>

      <template v-else>
        <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
        <div v-else-if="error" class="error">{{ error }}</div>
        <template v-else>
          <div v-if="recommendations.length === 0" class="empty-state">
            {{ t('restocking.recommendations.empty') }}
          </div>
          <template v-else>
            <div class="table-container">
              <table>
                <thead>
                  <tr>
                    <th>{{ t('restocking.table.sku') }}</th>
                    <th>{{ t('restocking.table.itemName') }}</th>
                    <th>{{ t('restocking.table.category') }}</th>
                    <th class="col-num">{{ t('restocking.table.currentDemand') }}</th>
                    <th class="col-num">{{ t('restocking.table.forecastedDemand') }}</th>
                    <th class="col-num">{{ t('restocking.table.demandGap') }}</th>
                    <th class="col-num">{{ t('restocking.table.qtyToRestock') }}</th>
                    <th class="col-num">{{ t('restocking.table.unitCost') }}</th>
                    <th class="col-num">{{ t('restocking.table.lineTotal') }}</th>
                    <th>{{ t('restocking.table.trend') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="rec in recommendations" :key="rec.sku">
                    <td><strong>{{ rec.sku }}</strong></td>
                    <td>{{ rec.item_name }}</td>
                    <td>{{ rec.category }}</td>
                    <td class="col-num">{{ rec.current_demand }}</td>
                    <td class="col-num"><strong>{{ rec.forecasted_demand }}</strong></td>
                    <td class="col-num">{{ rec.demand_gap }}</td>
                    <td class="col-num">{{ rec.recommended_quantity }}</td>
                    <td class="col-num">{{ currencySymbol }}{{ rec.unit_cost.toLocaleString() }}</td>
                    <td class="col-num"><strong>{{ currencySymbol }}{{ rec.line_total.toLocaleString() }}</strong></td>
                    <td>
                      <span :class="['badge', rec.trend]">{{ t('trends.' + rec.trend) }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Summary row -->
            <div class="recommendations-summary">
              <div class="summary-item">
                <span class="summary-label">{{ t('restocking.recommendations.itemsSelected') }}</span>
                <span class="summary-value">{{ responseData.item_count }}</span>
              </div>
              <div class="summary-item">
                <span class="summary-label">{{ t('restocking.recommendations.totalCost') }}</span>
                <span class="summary-value cost">{{ currencySymbol }}{{ responseData.total_cost.toLocaleString() }}</span>
              </div>
              <div class="summary-item">
                <span class="summary-label">{{ t('restocking.recommendations.budgetRemaining') }}</span>
                <span class="summary-value remaining">{{ currencySymbol }}{{ responseData.budget_remaining.toLocaleString() }}</span>
              </div>
            </div>
          </template>

          <!-- Place Order button -->
          <div class="place-order-row">
            <button
              class="btn-primary"
              :disabled="recommendations.length === 0 || submitting"
              @click="placeOrder"
            >
              {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
            </button>
          </div>
        </template>
      </template>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()
    const router = useRouter()

    const currencySymbol = computed(() => currentCurrency.value === 'JPY' ? '¥' : '$')

    const budget = ref(100000)
    const loading = ref(false)
    const error = ref(null)
    const submitting = ref(false)
    const submittedOrder = ref(null)

    // Full API response kept so summary fields are accessible
    const responseData = ref({
      budget: 0,
      total_cost: 0,
      budget_remaining: 0,
      item_count: 0,
      recommendations: []
    })

    const recommendations = computed(() => responseData.value.recommendations)

    const fetchRecommendations = async () => {
      loading.value = true
      error.value = null
      try {
        const data = await api.getRestockRecommendations(budget.value)
        responseData.value = data
      } catch (err) {
        error.value = t('restocking.errorMessage')
        console.error(err)
      } finally {
        loading.value = false
      }
    }

    // Debounce slider changes so the API isn't hammered on every tick
    let debounceTimer = null
    watch(budget, () => {
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(fetchRecommendations, 300)
    })

    const placeOrder = async () => {
      submitting.value = true
      error.value = null
      try {
        const items = recommendations.value.map(r => ({
          sku: r.sku,
          quantity: r.recommended_quantity
        }))
        const order = await api.submitRestockOrder({ budget: budget.value, items })
        submittedOrder.value = order
      } catch (err) {
        error.value = t('restocking.errorMessage')
        console.error(err)
      } finally {
        submitting.value = false
      }
    }

    const goToOrders = () => {
      router.push('/orders')
    }

    const resetState = () => {
      submittedOrder.value = null
      fetchRecommendations()
    }

    // Fetch immediately on mount — no debounce needed for initial load
    onMounted(fetchRecommendations)

    return {
      t,
      currencySymbol,
      budget,
      loading,
      error,
      submitting,
      submittedOrder,
      responseData,
      recommendations,
      placeOrder,
      goToOrders,
      resetState
    }
  }
}
</script>

<style scoped>
/* Budget card body */
.budget-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 1rem 0 0.5rem;
  gap: 0.5rem;
}

.budget-value {
  font-size: 2.5rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.budget-sublabel {
  font-size: 0.875rem;
  color: #64748b;
  margin-bottom: 0.5rem;
}

/* Slider — cross-browser styled */
.budget-slider {
  width: 100%;
  max-width: 600px;
  height: 6px;
  appearance: none;
  -webkit-appearance: none;
  background: #e2e8f0;
  border-radius: 3px;
  outline: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
  border: 2px solid white;
  box-shadow: 0 1px 4px rgba(59, 130, 246, 0.4);
  transition: background 0.2s, box-shadow 0.2s;
}

.budget-slider::-webkit-slider-thumb:hover {
  background: #2563eb;
  box-shadow: 0 2px 6px rgba(37, 99, 235, 0.5);
}

.budget-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #3b82f6;
  cursor: pointer;
  border: 2px solid white;
  box-shadow: 0 1px 4px rgba(59, 130, 246, 0.4);
}

.budget-slider::-moz-range-thumb:hover {
  background: #2563eb;
}

.slider-range-labels {
  width: 100%;
  max-width: 600px;
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: #94a3b8;
  margin-top: 0.25rem;
}

/* Right-align numeric columns */
.col-num {
  text-align: right;
}

/* Recommendations summary row */
.recommendations-summary {
  display: flex;
  gap: 2rem;
  padding: 1rem 0.75rem;
  background: #f8fafc;
  border-top: 1px solid #e2e8f0;
  border-radius: 0 0 6px 6px;
  flex-wrap: wrap;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.summary-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.summary-value {
  font-size: 1.125rem;
  font-weight: 700;
  color: #0f172a;
}

.summary-value.cost {
  color: #0f172a;
}

.summary-value.remaining {
  color: #059669;
}

/* Place order row */
.place-order-row {
  display: flex;
  justify-content: flex-end;
  padding: 1rem 0 0.25rem;
}

.btn-primary {
  background: #3b82f6;
  color: white;
  border: none;
  padding: 0.625rem 1.5rem;
  border-radius: 6px;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, opacity 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Secondary button for success actions */
.btn-secondary {
  background: white;
  color: #3b82f6;
  border: 1px solid #3b82f6;
  padding: 0.625rem 1.5rem;
  border-radius: 6px;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.btn-secondary:hover {
  background: #eff6ff;
}

/* Empty state */
.empty-state {
  padding: 2.5rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

/* Success block */
.success-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 2.5rem 1.5rem;
  text-align: center;
}

.success-title {
  font-size: 1.375rem;
  font-weight: 700;
  color: #059669;
}

.success-message {
  font-size: 0.938rem;
  color: #334155;
  max-width: 480px;
}

.success-actions {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  justify-content: center;
  margin-top: 0.5rem;
}
</style>
